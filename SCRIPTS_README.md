# Scripts Directory - Usage Guide

## Active Scripts

### `add_sample_availability_simple.py`
**Purpose**: Add sample availability patterns for practitioners (max 7 hours per week each)  
**Usage**: `python scripts/add_sample_availability_simple.py`  
**Note**: Uses direct database access, no Flask context needed

### `add_sample_appointments.py`
**Purpose**: Add sample appointments for existing patients  
**Usage**: `python scripts/add_sample_appointments.py`  
**Note**: Uses direct database access, no Flask context needed

### `create_admin.py`
**Purpose**: Create or reset the admin user in the local database  
**Usage**: `python scripts/create_admin.py`  
**Note**: For local development only

## Production Scripts

### `create_admin_job.py` (root directory)
**Purpose**: Create admin user in production (Cloud Run job)  
**Usage**: Run as Cloud Run job or in production environment  
**Note**: Sets production environment variables automatically

## Obsolete Scripts (Do Not Use)

### `add_sample_availability.py`
**Status**: Obsolete - replaced by `add_sample_availability_simple.py`  
**Reason**: More complex, requires Flask context, harder to maintain

### `generate_demo_data.py`
**Status**: May be obsolete - check if still needed  
**Reason**: May have been replaced by individual sample data scripts

### `init_db.py`
**Status**: Check if still needed  
**Reason**: Database initialization may be handled by Flask-Migrate

## Running Scripts

All scripts should be run from the project root directory:

```bash
# Activate virtual environment first
source venv/bin/activate

# Run script
python scripts/script_name.py
```


