# backend/app/api/comments.py
"""
Comments API for Collaboration
Threaded comments on BoQ and BBS items
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.comment import Comment
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/comments", tags=["Comments"])


class CommentCreate(BaseModel):
    comment_text: str
    boq_item_id: Optional[UUID] = None
    bbs_item_id: Optional[UUID] = None
    parent_comment_id: Optional[UUID] = None


class CommentUpdate(BaseModel):
    comment_text: str
    is_resolved: Optional[bool] = None


class CommentResponse(BaseModel):
    id: str
    user_id: str
    user_name: str
    comment_text: str
    boq_item_id: Optional[str]
    bbs_item_id: Optional[str]
    parent_comment_id: Optional[str]
    is_resolved: bool
    created_at: datetime
    updated_at: datetime
    replies: List['CommentResponse'] = []
    
    class Config:
        from_attributes = True


@router.post("/", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new comment"""
    if not comment_data.boq_item_id and not comment_data.bbs_item_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comment must be attached to either BoQ or BBS item"
        )
    
    comment = Comment(
        user_id=current_user.id,
        comment_text=comment_data.comment_text,
        boq_item_id=comment_data.boq_item_id,
        bbs_item_id=comment_data.bbs_item_id,
        parent_comment_id=comment_data.parent_comment_id
    )
    
    db.add(comment)
    db.commit()
    db.refresh(comment)
    
    # Add user name to response
    response_dict = CommentResponse.from_orm(comment).dict()
    response_dict['user_name'] = current_user.full_name
    
    return response_dict


@router.get("/boq/{boq_item_id}", response_model=List[CommentResponse])
async def get_boq_comments(
    boq_item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all comments for a BoQ item"""
    comments = db.query(Comment).filter(
        Comment.boq_item_id == boq_item_id,
        Comment.parent_comment_id == None  # Only root comments
    ).order_by(Comment.created_at.desc()).all()
    
    # Build response with user names and replies
    result = []
    for comment in comments:
        comment_dict = CommentResponse.from_orm(comment).dict()
        comment_dict['user_name'] = comment.user.full_name
        
        # Get replies
        replies = db.query(Comment).filter(
            Comment.parent_comment_id == comment.id
        ).all()
        comment_dict['replies'] = [
            {**CommentResponse.from_orm(r).dict(), 'user_name': r.user.full_name}
            for r in replies
        ]
        
        result.append(comment_dict)
    
    return result


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: UUID,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a comment"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    if comment.user_id != current_user.id and not current_user.is_super_user():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own comments"
        )
    
    comment.comment_text = comment_data.comment_text
    if comment_data.is_resolved is not None:
        comment.is_resolved = comment_data.is_resolved
        if comment_data.is_resolved:
            comment.resolved_at = datetime.utcnow()
    
    db.commit()
    db.refresh(comment)
    
    response_dict = CommentResponse.from_orm(comment).dict()
    response_dict['user_name'] = comment.user.full_name
    
    return response_dict


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a comment"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    if comment.user_id != current_user.id and not current_user.is_super_user():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own comments"
        )
    
    db.delete(comment)
    db.commit()
    
    return None


# backend/app/api/sitelogs.py
"""
Site Logs API
Daily site progress reporting
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.sitelog import SiteLog
from app.models.project import Project
from app.services.auth_service import get_current_user, PermissionChecker

router = APIRouter(prefix="/api/sitelogs", tags=["Site Logs"])


class SiteLogCreate(BaseModel):
    log_text: str
    weather_conditions: Optional[str] = None
    workforce_count: Optional[int] = None
    equipment_used: Optional[List[str]] = []
    activities_completed: Optional[List[str]] = []
    issues_encountered: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteLogResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    user_name: str
    log_date: datetime
    log_text: str
    weather_conditions: Optional[str]
    workforce_count: Optional[int]
    photo_urls: List[str]
    latitude: Optional[float]
    longitude: Optional[float]
    is_synced: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/{project_id}", response_model=SiteLogResponse, status_code=status.HTTP_201_CREATED)
async def create_site_log(
    project_id: UUID,
    log_data: SiteLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new site log entry"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to add site logs to this project"
        )
    
    site_log = SiteLog(
        project_id=project_id,
        user_id=current_user.id,
        log_text=log_data.log_text,
        weather_conditions=log_data.weather_conditions,
        workforce_count=log_data.workforce_count,
        equipment_used=log_data.equipment_used,
        activities_completed=log_data.activities_completed,
        issues_encountered=log_data.issues_encountered,
        latitude=log_data.latitude,
        longitude=log_data.longitude,
        is_synced=True
    )
    
    db.add(site_log)
    db.commit()
    db.refresh(site_log)
    
    response_dict = SiteLogResponse.from_orm(site_log).dict()
    response_dict['user_name'] = current_user.full_name
    
    return response_dict


@router.get("/{project_id}", response_model=List[SiteLogResponse])
async def get_site_logs(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all site logs for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if not PermissionChecker.can_view_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view site logs for this project"
        )
    
    logs = db.query(SiteLog).filter(
        SiteLog.project_id == project_id
    ).order_by(SiteLog.log_date.desc()).all()
    
    result = []
    for log in logs:
        log_dict = SiteLogResponse.from_orm(log).dict()
        log_dict['user_name'] = log.user.full_name
        result.append(log_dict)
    
    return result


# backend/app/api/expenses.py
"""
Expenses API for Budget Tracking
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.expense import Expense
from app.models.project import Project
from app.services.auth_service import get_current_user, PermissionChecker

router = APIRouter(prefix="/api/expenses", tags=["Expenses"])


class ExpenseCreate(BaseModel):
    expense_date: datetime
    category: str
    item_description: str
    supplier: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_amount: float
    remarks: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: str
    project_id: str
    expense_date: datetime
    category: str
    item_description: str
    supplier: Optional[str]
    total_amount: float
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/{project_id}", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    project_id: UUID,
    expense_data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record a new expense"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    expense = Expense(
        project_id=project_id,
        user_id=current_user.id,
        **expense_data.dict()
    )
    
    db.add(expense)
    db.commit()
    db.refresh(expense)
    
    # Update actual cost
    project.actual_cost = db.query(
        func.sum(Expense.total_amount)
    ).filter(Expense.project_id == project_id).scalar() or 0.0
    db.commit()
    
    return expense


@router.get("/{project_id}", response_model=List[ExpenseResponse])
async def get_expenses(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all expenses for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    expenses = db.query(Expense).filter(
        Expense.project_id == project_id
    ).order_by(Expense.expense_date.desc()).all()
    
    return expenses


@router.get("/{project_id}/variance")
async def get_budget_variance(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate budget variance"""
    from sqlalchemy import func
    
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get category breakdown
    category_expenses = db.query(
        Expense.category,
        func.sum(Expense.total_amount).label('actual')
    ).filter(
        Expense.project_id == project_id
    ).group_by(Expense.category).all()
    
    variance_data = {
        "estimated_total": project.estimated_cost,
        "actual_total": project.actual_cost,
        "variance": project.estimated_cost - project.actual_cost,
        "variance_percentage": (
            ((project.estimated_cost - project.actual_cost) / project.estimated_cost * 100)
            if project.estimated_cost > 0 else 0
        ),
        "categories": [
            {
                "category": cat,
                "actual": float(actual)
            }
            for cat, actual in category_expenses
        ]
    }
    
    return variance_data


# backend/app/api/reports.py
"""
Reports API - Download Endpoints
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
import io

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.services.auth_service import get_current_user, PermissionChecker
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/{project_id}/boq/excel")
async def download_boq_excel(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download BoQ as Excel file"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if not PermissionChecker.can_view_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to download reports for this project"
        )
    
    report_service = ReportService(project, db)
    excel_file = report_service.generate_boq_excel()
    
    filename = f"{project.name.replace(' ', '_')}_BoQ.xlsx"
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/bbs/excel")
async def download_bbs_excel(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download BBS as Excel file"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    report_service = ReportService(project, db)
    excel_file = report_service.generate_bbs_excel()
    
    filename = f"{project.name.replace(' ', '_')}_BBS.xlsx"
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/boq/pdf")
async def download_boq_pdf(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download BoQ as PDF"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    report_service = ReportService(project, db)
    pdf_file = report_service.generate_boq_pdf()
    
    filename = f"{project.name.replace(' ', '_')}_BoQ.pdf"
    
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/cost-summary/pdf")
async def download_cost_summary(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download cost summary as PDF"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    report_service = ReportService(project, db)
    pdf_file = report_service.generate_cost_summary_pdf()
    
    filename = f"{project.name.replace(' ', '_')}_CostSummary.pdf"
    
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Update main.py to include new routers
"""
Add to app/main.py:

from app.api import comments, sitelogs, expenses, reports

app.include_router(comments.router)
app.include_router(sitelogs.router)
app.include_router(expenses.router)
app.include_router(reports.router)
"""
