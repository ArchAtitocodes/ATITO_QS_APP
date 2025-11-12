# backend/app/backend_config.py
"""
ATITO QS App - Configuration Management
Secure configuration with environment variables
Author: Eng. STEPHEN ODHIAMBO
"""

from pydantic_settings import BaseSettings
from pydantic import validator
from typing import Optional
import secrets


class Settings(BaseSettings):
    """Application configuration settings"""
    
    # Application
    APP_NAME: str = "ATITO QS App"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days for persistent login
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 86400  # 60 days
    
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: set = {
        "pdf", "dwg", "dxf", "ifc", "png", "jpg", "jpeg"
    }
    
    # AI/ML Configuration
    MODEL_PATH: str = "models/yolov8n.pt"
    AI_CONFIDENCE_THRESHOLD: float = 0.80
    OCR_CONFIDENCE_THRESHOLD: float = 0.80
    
    # Google Vision API
    GOOGLE_VISION_API_KEY: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    
    # External APIs & Scraping
    IQSK_BASE_URL: str = "https://www.iqsk.org"
    NCA_BASE_URL: str = "https://nca.go.ke"
    KIPPRA_BASE_URL: str = "https://kippra.or.ke"
    INTEGRUM_BASE_URL: str = "https://integrum.co.ke"
    
    SCRAPING_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    SCRAPING_RATE_LIMIT: int = 1  # seconds between requests
    
    # M-Pesa Configuration
    MPESA_CONSUMER_KEY: str
    MPESA_CONSUMER_SECRET: str
    MPESA_PASSKEY: str
    MPESA_SHORTCODE: str = "174379"  # Business shortcode
    MPESA_CALLBACK_URL: str
    MPESA_SAFARICOM_PHONE: str = "+254701453230"
    MPESA_AIRTEL_PHONE: str = "+254102015805"
    
    # Pricing Configuration
    PROVISIONAL_SUM_PERCENTAGE: float = 0.10
    PRELIMINARY_COST_PERCENTAGE: float = 0.05
    LABOR_OVERHEADS_PERCENTAGE: float = 0.50
    VAT_PERCENTAGE: float = 0.16
    DEFAULT_CONTINGENCY_PERCENTAGE: float = 0.10
    
    # Waste Factors
    WASTE_CONCRETE: float = 1.20
    WASTE_BLOCKWORK: float = 1.05
    WASTE_REINFORCEMENT: float = 1.10
    WASTE_FORMWORK: float = 1.10
    WASTE_TILES: float = 1.10
    WASTE_PAINT: float = 1.07
    WASTE_PIPES: float = 1.05
    WASTE_ROOFING: float = 1.05
    WASTE_ELECTRICAL: float = 1.10
    
    # Subscription Plans
    FREE_TRIAL_DAYS: int = 30
    FREE_DAILY_TOKEN_LIMIT: int = 50
    FREE_MAX_PROJECTS: int = 1
    FREE_MAX_FLOORS: int = 1
    
    PRO_MONTHLY_COST: float = 500.00  # KES
    PRO_DAILY_PROJECT_LIMIT: int = 8
    PRO_MAX_FLOORS: int = 5
    
    BUSINESS_MONTHLY_COST: float = 2000.00  # KES
    BUSINESS_MAX_FLOORS: int = 10
    
    # Super User Emails
    SUPER_USER_EMAILS: list = [
        "stephenodhiambo008@gmail.com",
        "stephenatito1994@gmail.com"
    ]
    
    # Email Configuration (for notifications)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    
    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Kenyan Counties
    KENYAN_COUNTIES: list = [
        "Nairobi", "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu",
        "Taita-Taveta", "Garissa", "Wajir", "Mandera", "Marsabit", "Isiolo",
        "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni",
        "Nyandarua", "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana",
        "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu", "Elgeyo-Marakwet",
        "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado",
        "Kericho", "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia",
        "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira"
    ]
    
    # Soil Types
    SOIL_TYPES: list = [
        "lateritic", "loam", "black_cotton", "sandy", "rock", "clay", "murram"
    ]
    
    # Structural Systems
    STRUCTURAL_SYSTEMS: list = [
        "rc_frame", "load_bearing", "steel", "composite", "masonry"
    ]
    
    # Building Use Types
    BUILDING_USES: list = [
        "residential", "commercial", "institutional", "industrial"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


# Create settings instance
settings = Settings()


# Kenyan County Location Factors for costing
COUNTY_LOCATION_FACTORS = {
    "Nairobi": 1.00,
    "Mombasa": 1.05,
    "Kisumu": 0.95,
    "Nakuru": 0.92,
    "Eldoret": 0.93,  # Uasin Gishu
    "Kiambu": 0.98,
    "Machakos": 0.90,
    "Kajiado": 0.92,
    "Nyeri": 0.91,
    "Meru": 0.88,
    # Add remaining counties with appropriate factors
    # Remote counties typically have higher factors due to transport costs
    "Turkana": 1.25,
    "Mandera": 1.30,
    "Wajir": 1.28,
    "Marsabit": 1.22,
    "Lamu": 1.15,
}


# Material Recipes per Unit (as per requirements)
MATERIAL_RECIPES = {
    "wall_per_sqm": {
        "cement_bags": 0.15,
        "river_sand_lorry": 0.005,
        "clay_bricks": 60,
        "hoop_iron_roll": 0.002,
        "t10_bars": 0.01,
        "nails_kg": 0.005,
        "blue_gum_6x1_ft": 1.5,
        "plaster_sqm": 2.0,
        "internal_paint_sqm": 2.0
    },
    "door_per_unit": {
        "steel_door_3x7": 0.5,
        "flush_door_3x7": 0.5,
        "frame_3x7": 1.0,
        "assorted_nails_kg": 0.5
    },
    "window_per_unit": {
        "steel_casement_window": 1.0,
        "putty_kg": 2.0,
        "paint_liter": 0.5
    },
    "slab_per_sqm": {
        "cement_bags": 1.0,
        "ballast_lorry": 0.01,
        "river_sand_lorry": 0.008,
        "t16_bars": 0.02,
        "t12_bars": 0.015,
        "binding_wire_rolls": 0.5,
        "polythene_rolls": 0.4,
        "hardcore_lorry": 0.01,
        "murram_lorry": 0.005,
        "anti_termite_liters": 0.1,
        "blue_gum_6x1_ft": 3.0,
        "cement_screed_sqm": 1.0,
        "floor_tiles_sqm": 1.0
    },
    "beam_per_meter": {
        "cement_bags": 0.2,
        "t12_bars": 0.01,
        "r6_bars": 0.005,
        "binding_wire_rolls": 0.0001,
        "blue_gum_6x1_ft": 0.8,
        "blades": 1.0
    },
    "column_per_unit": {
        "cement_bags": 0.08,
        "t16_bars": 0.01,
        "r6_bars": 0.003,
        "binding_wire_rolls": 0.0001,
        "blue_gum_6x1_ft": 1.5
    },
    "roof_per_sqm": {
        "blue_gum_3x2_ft": 3.5,
        "blue_gum_4x2_ft": 3.5,
        "g28_gi_sheet_sqm": 2.64,
        "nails_kg": 0.5,
        "roofing_nails_kg": 0.5
    }
}


# BoQ Categories in proper order
BOQ_CATEGORIES = [
    "preliminaries",
    "substructure",
    "superstructure",
    "roofing",
    "finishes",
    "services",
    "external_works",
    "provisional_sums"
]


# BS 8666 Bar Bending Shape Codes
BS8666_SHAPE_CODES = {
    "00": "Straight",
    "11": "L-Bar",
    "12": "T-Bar",
    "13": "U-Bar",
    "20": "Stirrup",
    "21": "Closed Stirrup",
    "23": "Link",
    "26": "Spiral",
    "27": "Column Starter",
    "29": "Trombone",
    "32": "Bent Bar",
    "41": "Spacer Bar",
    "51": "Chair Bar",
    "77": "Helical",
    "99": "Special"
}


# BS 8666 Bend Allowances (mm)
BS8666_BEND_ALLOWANCES = {
    6: 20,   # R6
    8: 25,   # R8/T8
    10: 30,  # T10
    12: 35,  # T12
    16: 45,  # T16
    20: 55,  # T20
    25: 70,  # T25
    32: 90,  # T32
    40: 110  # T40
}
