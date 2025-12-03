from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, User, AvailabilityPattern, AvailabilityException, Patient
from datetime import date, timedelta
import logging

# Create blueprints
api_bp = Blueprint('api', __name__)

logger = logging.getLogger(__name__)

# --- API Routes ---

@api_bp.route('/users/practitioners')
@login_required
def get_practitioners():
    """Get all active users (practitioners/nurses) with their colors"""
    try:
        users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'name': user.full_name,
                'role': user.role or '',
                'color': user.calendar_color or '#3b82f6'
            })
        
        return jsonify({'success': True, 'users': user_list})
    except Exception as e:
        logger.error(f"Error fetching practitioners: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/public-holidays')
@login_required
def get_public_holidays():
    """Get Australian public holidays for the current year and next year"""
    try:
        current_year = date.today().year
        holidays = []
        
        # Australian public holidays (nationwide)
        # Format: (month, day, name)
        au_holidays_template = [
            (1, 1, "New Year's Day"),
            (1, 26, "Australia Day"),
            (4, 25, "ANZAC Day"),
            (12, 25, "Christmas Day"),
            (12, 26, "Boxing Day")
        ]
        
        # Generate holidays for current year and next year
        for year in [current_year, current_year + 1]:
            for month, day, name in au_holidays_template:
                holidays.append({
                    'date': f'{year}-{month:02d}-{day:02d}',
                    'name': name,
                    'type': 'public_holiday'
                })
            
            # Easter-related holidays (approximate - would need proper calculation)
            # Good Friday (varies, approximate for 2025-2026)
            if year == 2025:
                holidays.append({'date': '2025-04-18', 'name': 'Good Friday', 'type': 'public_holiday'})
                holidays.append({'date': '2025-04-21', 'name': 'Easter Monday', 'type': 'public_holiday'})
            elif year == 2026:
                holidays.append({'date': '2026-04-03', 'name': 'Good Friday', 'type': 'public_holiday'})
                holidays.append({'date': '2026-04-06', 'name': 'Easter Monday', 'type': 'public_holiday'})
            
            # Queen's/King's Birthday (second Monday in June)
            june_1 = date(year, 6, 1)
            days_to_monday = (7 - june_1.weekday()) % 7
            if days_to_monday == 0:
                days_to_monday = 7
            first_monday = june_1 + timedelta(days=days_to_monday)
            second_monday = first_monday + timedelta(days=7)
            holidays.append({
                'date': second_monday.isoformat(),
                'name': "King's Birthday",
                'type': 'public_holiday'
            })
        
        return jsonify({
            'success': True,
            'holidays': holidays
        })
    except Exception as e:
        logger.error(f"Error fetching public holidays: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/team-availability')
@login_required
def get_team_availability():
    """Get availability patterns and exceptions for selected users"""
    try:
        # Get user filter from query params
        user_ids_str = request.args.get('users', '')
        user_ids = []
        if user_ids_str:
            try:
                user_ids = [int(uid) for uid in user_ids_str.split(',') if uid.strip()]
            except (ValueError, TypeError):
                user_ids = []
        
        # Query patterns
        pattern_query = AvailabilityPattern.query.join(User).filter(User.is_active == True)
        if user_ids:
            pattern_query = pattern_query.filter(AvailabilityPattern.user_id.in_(user_ids))
        
        patterns = pattern_query.all()
        
        # Query exceptions
        exception_query = AvailabilityException.query.join(User).filter(User.is_active == True)
        if user_ids:
            exception_query = exception_query.filter(AvailabilityException.user_id.in_(user_ids))
        
        exceptions = exception_query.all()
        
        # Format patterns
        pattern_list = []
        for pattern in patterns:
            try:
                pattern_list.append({
                    'id': pattern.id,
                    'user_id': pattern.user_id,
                    'user_name': pattern.user.full_name if pattern.user else 'Unknown',
                    'user_color': pattern.user.calendar_color if pattern.user and pattern.user.calendar_color else '#3b82f6',
                    'title': pattern.title or '',
                    'frequency': pattern.frequency or 'weekly',
                    'weekdays': pattern.weekdays or [],
                    'start_time': pattern.start_time.strftime('%H:%M') if pattern.start_time else None,
                    'end_time': pattern.end_time.strftime('%H:%M') if pattern.end_time else None,
                    'valid_from': pattern.valid_from.isoformat() if pattern.valid_from else None,
                    'valid_until': pattern.valid_until.isoformat() if pattern.valid_until else None,
                    'is_active': pattern.is_active if hasattr(pattern, 'is_active') else True
                })
            except Exception as pattern_error:
                logger.warning(f"Error formatting pattern {pattern.id}: {pattern_error}")
                continue
        
        # Format exceptions
        exception_list = []
        for exception in exceptions:
            try:
                exception_list.append({
                    'id': exception.id,
                    'user_id': exception.user_id,
                    'user_name': exception.user.full_name if exception.user else 'Unknown',
                    'exception_date': exception.exception_date.isoformat() if hasattr(exception.exception_date, 'isoformat') else str(exception.exception_date),
                    'exception_type': exception.exception_type or 'blocked',
                    'is_all_day': exception.is_all_day if hasattr(exception, 'is_all_day') else True,
                    'start_time': exception.start_time.strftime('%H:%M') if exception.start_time else None,
                    'end_time': exception.end_time.strftime('%H:%M') if exception.end_time else None,
                    'reason': exception.reason or ''
                })
            except Exception as exception_error:
                logger.warning(f"Error formatting exception {exception.id}: {exception_error}")
                continue
        
        return jsonify({
            'success': True,
            'patterns': pattern_list,
            'exceptions': exception_list
        })
    except Exception as e:
        logger.error(f"Error fetching team availability: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/migrate/show-in-patient-app', methods=['POST'])
def migrate_show_in_patient_app():
    """One-time migration: Add show_in_patient_app column to target_ranges (no auth required)"""
    try:
        from sqlalchemy import text
        
        # Check if column already exists
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='target_ranges' 
            AND column_name='show_in_patient_app'
        """))
        
        if result.fetchone():
            return jsonify({
                'success': True,
                'message': 'Column already exists',
                'already_exists': True
            })
        
        # Add column
        db.session.execute(text("""
            ALTER TABLE target_ranges 
            ADD COLUMN show_in_patient_app BOOLEAN DEFAULT TRUE
        """))
        db.session.commit()
        
        # Update existing rows
        db.session.execute(text("""
            UPDATE target_ranges 
            SET show_in_patient_app = TRUE 
            WHERE show_in_patient_app IS NULL
        """))
        db.session.commit()
        
        logger.info("✅ Migration completed: Added show_in_patient_app column")
        return jsonify({
            'success': True,
            'message': 'Migration completed successfully',
            'already_exists': False
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Migration error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/migrate/create-indexes', methods=['POST'])
def create_database_indexes():
    """Create performance indexes (no auth required)"""
    try:
        from sqlalchemy import text
        
        indexes = [
            ("idx_health_data_patient_timestamp", """
                CREATE INDEX IF NOT EXISTS idx_health_data_patient_timestamp 
                ON health_data(patient_id, timestamp DESC)
            """),
            ("idx_health_data_measurement_type", """
                CREATE INDEX IF NOT EXISTS idx_health_data_measurement_type 
                ON health_data(measurement_type)
            """),
            ("idx_health_data_patient_type_timestamp", """
                CREATE INDEX IF NOT EXISTS idx_health_data_patient_type_timestamp 
                ON health_data(patient_id, measurement_type, timestamp DESC)
            """),
            ("idx_target_ranges_patient_measurement", """
                CREATE INDEX IF NOT EXISTS idx_target_ranges_patient_measurement 
                ON target_ranges(patient_id, measurement_type)
            """),
            ("idx_target_ranges_show_in_app", """
                CREATE INDEX IF NOT EXISTS idx_target_ranges_show_in_app 
                ON target_ranges(show_in_patient_app) 
                WHERE show_in_patient_app = TRUE
            """),
            ("idx_appointments_patient_date", """
                CREATE INDEX IF NOT EXISTS idx_appointments_patient_date 
                ON appointments(patient_id, start_time DESC)
            """),
            ("idx_devices_patient_id", """
                CREATE INDEX IF NOT EXISTS idx_devices_patient_id 
                ON devices(patient_id)
            """),
        ]
        
        # Try to create patient_auth indexes if table exists
        try:
            db.session.execute(text("SELECT 1 FROM patient_auth LIMIT 1"))
            indexes.extend([
                ("idx_patient_auth_patient_id", """
                    CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id 
                    ON patient_auth(patient_id)
                """),
                ("idx_patient_auth_email", """
                    CREATE INDEX IF NOT EXISTS idx_patient_auth_email 
                    ON patient_auth(email)
                """),
            ])
        except Exception:
            pass  # Table doesn't exist, skip those indexes
        
        created = []
        skipped = []
        errors = []
        
        for index_name, sql in indexes:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                created.append(index_name)
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    skipped.append(index_name)
                else:
                    errors.append(f"{index_name}: {str(e)}")
        
        return jsonify({
            'success': True,
            'created': created,
            'skipped': skipped,
            'errors': errors,
            'summary': f"{len(created)} created, {len(skipped)} already existed, {len(errors)} errors"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Index creation error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
