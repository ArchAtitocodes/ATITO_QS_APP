# backend/app/api/projects.py
"""
Projects API Endpoints
CRUD operations for construction projects
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.services.auth_service import get_current_user, validate_subscription, PermissionChecker
from app.models.audit import AuditLog
from pydantic import BaseModel
from datetime import datetime


# Pydantic schemas
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    county: Optional[str] = None
    client_type: Optional[str] = None
    soil_type: Optional[str] = None
    structural_system: Optional[str] = None
    building_use: Optional[str] = None
    number_of_floors: Optional[int] = None
    floor_area: Optional[float] = None
    contingency_percentage: Optional[float] = 0.10


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    county: Optional[str] = None
    status: Optional[ProjectStatus] = None
    number_of_floors: Optional[int] = None
    floor_area: Optional[float] = None
    contingency_percentage: Optional[float] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: ProjectStatus
    location: Optional[str]
    county: Optional[str]
    number_of_floors: Optional[int]
    floor_area: Optional[float]
    total_gfa: Optional[float]
    estimated_cost: float
    ai_confidence_score: float
    needs_review: List
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(validate_subscription),
    db: Session = Depends(get_db)
):
    """
    Create a new project
    
    Validates:
    - User subscription limits
    - Maximum floors based on plan
    - Project count limits
    """
    # Check if user can create more projects
    existing_projects = db.query(Project).filter(
        Project.owner_id == current_user.id,
        Project.status != ProjectStatus.ARCHIVED
    ).count()
    
    if not PermissionChecker.can_create_project(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project limit reached for {current_user.subscription_plan.value} plan"
        )
    
    # Validate floors limit
    if project_data.number_of_floors:
        max_floors = current_user.get_max_floors()
        if project_data.number_of_floors > max_floors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Floor limit is {max_floors} for {current_user.subscription_plan.value} plan"
            )
    
    # Calculate total GFA
    total_gfa = None
    if project_data.floor_area and project_data.number_of_floors:
        total_gfa = project_data.floor_area * project_data.number_of_floors
    
    # Create project
    new_project = Project(
        owner_id=current_user.id,
        name=project_data.name,
        description=project_data.description,
        location=project_data.location,
        county=project_data.county,
        client_type=project_data.client_type,
        soil_type=project_data.soil_type,
        structural_system=project_data.structural_system,
        building_use=project_data.building_use,
        number_of_floors=project_data.number_of_floors,
        floor_area=project_data.floor_area,
        total_gfa=total_gfa,
        contingency_percentage=project_data.contingency_percentage,
        status=ProjectStatus.DRAFT
    )
    
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action_type="PROJECT_CREATED",
        resource_type="PROJECT",
        resource_id=new_project.id,
        description=f"Created project: {new_project.name}",
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    # Update daily token count for free users
    if current_user.subscription_plan.value == "free":
        current_user.daily_token_count += 1
        db.commit()
    
    return new_project


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    status: Optional[ProjectStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all projects for current user
    
    Supports filtering by status and pagination
    """
    query = db.query(Project).filter(Project.owner_id == current_user.id)
    
    if status:
        query = query.filter(Project.status == status)
    
    projects = query.order_by(Project.created_at.desc()).offset(skip).limit(limit).all()
    
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific project by ID
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_view_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project"
        )
    
    # Update last accessed
    project.last_accessed = datetime.utcnow()
    db.commit()
    
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update project details
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this project"
        )
    
    # Update fields
    update_data = project_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    # Recalculate GFA if needed
    if project_data.floor_area or project_data.number_of_floors:
        if project.floor_area and project.number_of_floors:
            project.total_gfa = project.floor_area * project.number_of_floors
    
    db.commit()
    db.refresh(project)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action_type="PROJECT_UPDATED",
        resource_type="PROJECT",
        resource_id=project.id,
        description=f"Updated project: {project.name}",
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a project (soft delete by setting status to ARCHIVED)
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_delete_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this project"
        )
    
    # Soft delete
    project.status = ProjectStatus.ARCHIVED
    db.commit()
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action_type="PROJECT_DELETED",
        resource_type="PROJECT",
        resource_id=project.id,
        description=f"Deleted project: {project.name}",
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    return None


@router.post("/{project_id}/finalize")
async def finalize_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Finalize project and create as-built documentation
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to finalize this project"
        )
    
    if project.is_finalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is already finalized"
        )
    
    # Mark as finalized
    project.is_finalized = True
    project.finalized_at = datetime.utcnow()
    project.status = ProjectStatus.FINALIZED
    
    db.commit()
    
    # TODO: Generate as-built reports
    
    return {
        "message": "Project finalized successfully",
        "project_id": str(project.id),
        "finalized_at": project.finalized_at
    }


# backend/app/api/uploads.py
"""
File Upload API Endpoints
Handles drawing file uploads and processing
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.services.auth_service import get_current_user, PermissionChecker
from app.services.file_service import FileService
from app.models.audit import AuditLog

router = APIRouter(prefix="/api/uploads", tags=["File Upload"])


@router.post("/{project_id}/files")
async def upload_files(
    project_id: UUID,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload drawing files to a project
    
    Supports: PDF, DWG, DXF, IFC, JPEG, PNG
    Maximum file size: 100MB per file
    """
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to upload files to this project"
        )
    
    # Save files
    uploaded_files = []
    
    for file in files:
        try:
            file_metadata = await FileService.save_upload_file(
                file=file,
                project_id=str(project_id),
                user_id=str(current_user.id)
            )
            uploaded_files.append(file_metadata)
        except HTTPException as e:
            # Continue with other files if one fails
            print(f"Error uploading {file.filename}: {str(e)}")
            continue
    
    if not uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were successfully uploaded"
        )
    
    # Update project
    project.uploaded_files = project.uploaded_files + uploaded_files
    project.status = ProjectStatus.PROCESSING
    db.commit()
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action_type="FILES_UPLOADED",
        resource_type="PROJECT",
        resource_id=project.id,
        description=f"Uploaded {len(uploaded_files)} files to project {project.name}",
        metadata={"files": [f["original_filename"] for f in uploaded_files]},
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    # TODO: Trigger background processing task
    # from app.workers.processing_tasks import process_project_files
    # process_project_files.delay(str(project_id))
    
    return {
        "message": f"Successfully uploaded {len(uploaded_files)} file(s)",
        "files": uploaded_files,
        "project_id": str(project_id),
        "status": "processing"
    }


@router.get("/{project_id}/files")
async def list_files(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all uploaded files for a project
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_view_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project"
        )
    
    return {
        "project_id": str(project_id),
        "files": project.uploaded_files,
        "total_files": len(project.uploaded_files)
    }


@router.delete("/{project_id}/files/{file_index}")
async def delete_file(
    project_id: UUID,
    file_index: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a specific file from a project
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete files from this project"
        )
    
    # Validate file index
    if file_index < 0 or file_index >= len(project.uploaded_files):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Get file info and delete from disk
    file_info = project.uploaded_files[file_index]
    FileService.delete_file(file_info["file_path"])
    
    # Remove from project
    project.uploaded_files.pop(file_index)
    db.commit()
    
    return {
        "message": "File deleted successfully",
        "deleted_file": file_info["original_filename"]
    }


@router.post("/{project_id}/process")
async def process_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger processing of uploaded files
    Starts the AI/ML pipeline
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check permissions
    if not PermissionChecker.can_edit_project(current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to process this project"
        )
    
    if not project.uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files uploaded. Please upload drawings first."
        )
    
    # Update status
    project.status = ProjectStatus.PROCESSING
    db.commit()
    
    # TODO: Trigger Celery task for processing
    # from app.workers.processing_tasks import process_project_pipeline
    # task = process_project_pipeline.delay(str(project_id))
    
    return {
        "message": "Processing started",
        "project_id": str(project_id),
        "status": "processing",
        "files_count": len(project.uploaded_files)
    }
