import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Base directory for data files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # credit_admin/
DATA_DIR = os.path.join(BASE_DIR, "data")

# Database
DB_FILE = os.getenv("OPENWEBUI_DATABASE_PATH", "")

# Database URLs - construct from components if not explicitly defined
DATABASE_URL = os.getenv("DATABASE_URL")
CREDIT_DATABASE_URL = os.getenv("CREDIT_DATABASE_URL")

# If DATABASE_URL is not defined, construct it from individual components
if not DATABASE_URL:
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    
    if all([db_host, db_port, db_name, db_user, db_password]):
        DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    else:
        logger.error("DATABASE_URL not defined and required DB_* environment variables are missing.")
        logger.error("Either set DATABASE_URL or provide: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        raise ValueError("Missing database configuration: DATABASE_URL or required DB_* environment variables not set")

# If CREDIT_DATABASE_URL is not defined, construct it from individual components
if not CREDIT_DATABASE_URL:
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_credit_name = os.getenv("DB_CREDIT_NAME")
    db_credit_user = os.getenv("DB_CREDIT_USER")
    db_credit_password = os.getenv("DB_CREDIT_PASSWORD")

    if all([db_host, db_port, db_credit_name, db_credit_user, db_credit_password]):
        CREDIT_DATABASE_URL = f"postgresql://{db_credit_user}:{db_credit_password}@{db_host}:{db_port}/{db_credit_name}"
    else:
        logger.error("CREDIT_DATABASE_URL not defined and required DB_CREDIT_* environment variables are missing.")
        logger.error("Either set CREDIT_DATABASE_URL or provide: DB_HOST, DB_PORT, DB_CREDIT_NAME, DB_CREDIT_USER, DB_CREDIT_PASSWORD")
        raise ValueError("Missing credit database configuration: CREDIT_DATABASE_URL or required DB_CREDIT_* environment variables not set")

# Default credits configuration
DEFAULT_GROUP_CREDITS = float(os.getenv("DEFAULT_GROUP_CREDITS", "1000"))
DEFAULT_USER_CREDITS = float(os.getenv("DEFAULT_USER_CREDITS", "1000"))

# Auto-apply group credits configuration
AUTO_APPLY_GROUP_CREDITS = os.getenv("AUTO_APPLY_GROUP_CREDITS", "true").lower() == "true"
