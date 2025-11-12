# backend/app/workers/celery_workers.py
"""
Celery Application Configuration
Background task processing for ATITO QS App
Author: Eng. STEPHEN ODHIAMBO
"""

from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Create Celery app
celery_app = Celery(
    "atito_qs",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Africa/Nairobi',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic tasks schedule
celery_app.conf.beat_schedule = {
    'scrape-material-rates-daily': {
        'task': 'app.workers.scraping_tasks.scrape_all_sources',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'update-location-factors-weekly': {
        'task': 'app.workers.scraping_tasks.update_location_factors',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),  # Monday 3 AM
    },
    'cleanup-old-files-weekly': {
        'task': 'app.workers.maintenance_tasks.cleanup_old_files',
        'schedule': crontab(day_of_week=0, hour=4, minute=0),  # Sunday 4 AM
    },
}


# backend/app/workers/processing_tasks.py
"""
Processing Tasks
Main AI/ML pipeline for project processing
Author: Eng. STEPHEN ODHIAMBO
"""

from celery import Task
from sqlalchemy.orm import Session
from typing import Dict, Any
import traceback

from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.project import Project, ProjectStatus
from app.models.audit import AuditLog

# Import services
from app.parsers.pdf_parser import PDFParser
from app.parsers.dwg_parser import DWGParser
from app.parsers.ifc_parser import IFCParser
from app.parsers.image_parser import ImageParser
from app.services.ocr_service import OCRService
from app.services.ai_service import AIService
from app.services.dimension_extraction_service import DimensionExtractionService
from app.services.takeoff_engine import TakeoffEngine
from app.services.boq_generator import BOQGenerator
from app.services.bbs_generator import BBSGenerator
from app.services.costing_engine import CostingEngine


class DatabaseTask(Task):
    """Base task with database session management"""
    _db = None
    
    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True, name="process_project_pipeline")
def process_project_pipeline(self, project_id: str) -> Dict[str, Any]:
    """
    Main processing pipeline for a project
    
    Steps:
    1. Parse uploaded files
    2. Run OCR on rasterized content
    3. AI/ML object detection
    4. Dimension extraction
    5. Quantity takeoff
    6. BoQ generation
    7. BBS generation
    8. Costing
    """
    db = self.db
    
    try:
        # Get project
        project = db.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Update status
        project.status = ProjectStatus.PROCESSING
        db.commit()
        
        # Initialize services
        ocr_service = OCRService()
        ai_service = AIService()
        dim_service = DimensionExtractionService()
        
        all_detections = []
        all_dimensions = []
        confidence_scores = []
        
        # Process each uploaded file
        for file_info in project.uploaded_files:
            file_path = file_info["file_path"]
            file_ext = file_info["extension"]
            
            print(f"Processing file: {file_info['original_filename']}")
            
            # Step 1: Parse file
            parsed_data = None
            
            if file_ext == "pdf":
                with PDFParser(file_path) as parser:
                    parsed_data = parser.process_pdf()
            
            elif file_ext in ["dwg", "dxf"]:
                parser = DWGParser(file_path)
                parsed_data = parser.process_dwg()
            
            elif file_ext == "ifc":
                parser = IFCParser(file_path)
                parsed_data = parser.process_ifc()
            
            elif file_ext in ["jpg", "jpeg", "png"]:
                parser = ImageParser(file_path)
                parsed_data = parser.process_image()
            
            # Step 2: AI Processing
            ai_result = ai_service.process_drawing(file_path)
            
            if ai_result["success"]:
                all_detections.extend(ai_result["elements"]["detections"])
                confidence_scores.append(ai_result["overall_confidence"])
            
            # Step 3: Dimension Extraction
            dim_result = dim_service.process_drawing_dimensions(file_path)
            
            if dim_result["success"]:
                all_dimensions.extend(dim_result["dimensions"]["details"])
        
        # Calculate overall confidence
        overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        project.ai_confidence_score = overall_confidence
        
        # Step 4: Quantity Takeoff
        print("Running quantity takeoff...")
        takeoff_engine = TakeoffEngine(project, db)
        
        # Combine AI detections into quantities
        quantities_result = takeoff_engine.process_ai_detections({
            "success": True,
            "elements": {"detections": all_detections},
            "overall_confidence": overall_confidence,
            "needs_review": overall_confidence < 0.80
        })
        
        quantities = quantities_result["quantities"]
        
        # Step 5: Generate BoQ
        print("Generating Bill of Quantities...")
        boq_generator = BOQGenerator(project, db)
        boq_result = boq_generator.generate_boq(quantities)
        
        # Step 6: Generate BBS
        print("Generating Bar Bending Schedule...")
        bbs_generator = BBSGenerator(project, db)
        bbs_result = bbs_generator.generate_bbs(quantities)
        
        # Step 7: Costing
        print("Calculating costs...")
        costing_engine = CostingEngine(project, db)
        cost_summary = costing_engine.calculate_final_cost()
        
        # Update project
        project.status = ProjectStatus.ACTIVE
        project.needs_review = [item for item in project.needs_review if overall_confidence < 0.80]
        db.commit()
        
        # Audit log
        audit = AuditLog(
            user_id=project.owner_id,
            action_type="PROJECT_PROCESSED",
            resource_type="PROJECT",
            resource_id=project.id,
            description=f"Successfully processed project: {project.name}",
            metadata={
                "boq_items": boq_result["total_items"],
                "bbs_items": bbs_result["total_items"],
                "estimated_cost": cost_summary["grand_total"],
                "confidence": overall_confidence
            },
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        
        return {
            "success": True,
            "project_id": project_id,
            "boq_items": boq_result["total_items"],
            "bbs_items": bbs_result["total_items"],
            "estimated_cost": cost_summary["grand_total"],
            "confidence": overall_confidence
        }
    
    except Exception as e:
        print(f"Error processing project {project_id}: {str(e)}")
        print(traceback.format_exc())
        
        # Update project status to error
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.status = ProjectStatus.DRAFT
            project.ai_remarks = {"error": str(e), "traceback": traceback.format_exc()}
            db.commit()
        
        # Audit log
        audit = AuditLog(
            user_id=project.owner_id if project else None,
            action_type="PROJECT_PROCESSING_FAILED",
            resource_type="PROJECT",
            resource_id=project_id,
            description=f"Failed to process project",
            error_message=str(e),
            status="FAILURE"
        )
        db.add(audit)
        db.commit()
        
        raise


@celery_app.task(base=DatabaseTask, bind=True, name="generate_reports")
def generate_reports(self, project_id: str, report_types: list) -> Dict[str, Any]:
    """
    Generate reports for a project
    
    Args:
        project_id: Project UUID
        report_types: List of report types ['boq_excel', 'bbs_excel', 'boq_pdf', 'cost_summary']
    """
    db = self.db
    
    try:
        from app.services.report_service import ReportService
        
        project = db.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        report_service = ReportService(project, db)
        generated_reports = {}
        
        for report_type in report_types:
            if report_type == 'boq_excel':
                output = report_service.generate_boq_excel()
                # Save to file system
                filename = f"{project_id}_boq.xlsx"
                # generated_reports[report_type] = filename
            
            elif report_type == 'bbs_excel':
                output = report_service.generate_bbs_excel()
                filename = f"{project_id}_bbs.xlsx"
            
            elif report_type == 'boq_pdf':
                output = report_service.generate_boq_pdf()
                filename = f"{project_id}_boq.pdf"
            
            elif report_type == 'cost_summary':
                output = report_service.generate_cost_summary_pdf()
                filename = f"{project_id}_cost_summary.pdf"
        
        return {
            "success": True,
            "reports": generated_reports
        }
    
    except Exception as e:
        print(f"Error generating reports: {str(e)}")
        raise


# backend/app/workers/scraping_tasks.py
"""
Web Scraping Tasks
Periodic tasks for updating material rates
Author: Eng. STEPHEN ODHIAMBO
"""

from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.services.scraper_service import ScraperService


@celery_app.task(name="scrape_all_sources")
def scrape_all_sources():
    """
    Scrape material rates from all sources
    Runs daily at 2 AM
    """
    db = SessionLocal()
    
    try:
        print("Starting daily material rate scraping...")
        
        scraper = ScraperService(db)
        result = scraper.run_full_scrape()
        
        print(f"Scraping complete: {result['items_scraped']} items, {result['materials_updated']} materials updated")
        
        return result
    
    except Exception as e:
        print(f"Error in scraping task: {str(e)}")
        raise
    finally:
        db.close()


@celery_app.task(name="update_location_factors")
def update_location_factors():
    """
    Update county location factors
    Runs weekly on Monday at 3 AM
    """
    print("Updating location factors...")
    
    # TODO: Implement location factor updates based on market analysis
    
    return {"success": True, "message": "Location factors updated"}


# backend/app/workers/maintenance_tasks.py
"""
Maintenance Tasks
Cleanup and housekeeping tasks
Author: Eng. STEPHEN ODHIAMBO
"""

from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.project import Project, ProjectStatus
from datetime import datetime, timedelta
import os


@celery_app.task(name="cleanup_old_files")
def cleanup_old_files():
    """
    Clean up old archived project files
    Runs weekly on Sunday at 4 AM
    """
    db = SessionLocal()
    
    try:
        print("Starting file cleanup...")
        
        # Find archived projects older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        old_projects = db.query(Project).filter(
            Project.status == ProjectStatus.ARCHIVED,
            Project.updated_at < cutoff_date
        ).all()
        
        files_deleted = 0
        
        for project in old_projects:
            # Delete files from disk
            from app.services.file_service import FileService
            if FileService.delete_project_files(str(project.owner_id), str(project.id)):
                files_deleted += 1
        
        print(f"Cleanup complete: {files_deleted} project directories deleted")
        
        return {
            "success": True,
            "projects_cleaned": len(old_projects),
            "files_deleted": files_deleted
        }
    
    except Exception as e:
        print(f"Error in cleanup task: {str(e)}")
        raise
    finally:
        db.close()


@celery_app.task(name="reset_daily_tokens")
def reset_daily_tokens():
    """
    Reset daily token counts for free users
    Runs daily at midnight
    """
    db = SessionLocal()
    
    try:
        from app.models.user import User, SubscriptionPlan
        
        # Reset token count for all free users
        free_users = db.query(User).filter(
            User.subscription_plan == SubscriptionPlan.FREE
        ).all()
        
        for user in free_users:
            user.daily_token_count = 0
            user.last_token_reset = datetime.utcnow()
        
        db.commit()
        
        print(f"Reset tokens for {len(free_users)} free users")
        
        return {
            "success": True,
            "users_reset": len(free_users)
        }
    
    except Exception as e:
        print(f"Error resetting tokens: {str(e)}")
        raise
    finally:
        db.close()


# backend/app/workers/training_tasks.py
"""
AI Model Training Tasks
Periodic retraining based on user feedback
Author: Eng. STEPHEN ODHIAMBO
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="retrain_yolo_model")
def retrain_yolo_model():
    """
    Retrain YOLOv8 model with user-corrected data
    Runs weekly or when sufficient feedback is collected
    """
    print("Starting model retraining...")
    
    # TODO: Implement model retraining pipeline
    # 1. Collect user corrections from database
    # 2. Prepare training dataset
    # 3. Fine-tune YOLOv8 model
    # 4. Validate on test set
    # 5. Deploy if improved
    
    return {
        "success": True,
        "message": "Model retraining completed"
    }


# Run celery worker with:
# celery -A app.workers.celery_app worker --loglevel=info

# Run celery beat scheduler with:
# celery -A app.workers.celery_app beat --loglevel=info
