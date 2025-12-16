"""
Company Assets Blueprint
Manages company-wide resources, documents, and links
"""
from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, desc
from ..models import db, CompanyAsset
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

company_assets_bp = Blueprint('company_assets', __name__)

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'zip'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@company_assets_bp.route('/company-assets')
@login_required
def assets_list():
    """Display all company assets"""
    category_filter = request.args.get('category', '')
    search_query = request.args.get('search', '')
    
    # Build query
    query = CompanyAsset.query
    
    if category_filter:
        query = query.filter(CompanyAsset.category == category_filter)
    
    if search_query:
        query = query.filter(
            or_(
                CompanyAsset.title.ilike(f'%{search_query}%'),
                CompanyAsset.description.ilike(f'%{search_query}%'),
                CompanyAsset.tags.ilike(f'%{search_query}%')
            )
        )
    
    # Order by pinned first, then by created date
    assets = query.order_by(desc(CompanyAsset.is_pinned), desc(CompanyAsset.created_at)).all()
    
    # Get all unique categories for filter dropdown
    categories = db.session.query(CompanyAsset.category).distinct().filter(
        CompanyAsset.category.isnot(None)
    ).all()
    categories = [cat[0] for cat in categories]
    
    return render_template('company_assets.html', 
                         assets=assets, 
                         categories=categories,
                         current_category=category_filter,
                         search_query=search_query)

@company_assets_bp.route('/api/company-assets', methods=['GET'])
@login_required
def get_assets_api():
    """Get all company assets as JSON"""
    assets = CompanyAsset.query.order_by(
        desc(CompanyAsset.is_pinned), 
        desc(CompanyAsset.created_at)
    ).all()
    
    return jsonify({
        'success': True,
        'assets': [asset.to_dict() for asset in assets]
    })

@company_assets_bp.route('/api/company-assets', methods=['POST'])
@login_required
def create_asset():
    """Create a new company asset (file upload or link)"""
    try:
        asset_type = request.form.get('asset_type', 'file')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        tags = request.form.get('tags', '').strip()
        
        if not title:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        # Create new asset
        asset = CompanyAsset(
            title=title,
            description=description,
            asset_type=asset_type,
            category=category if category else None,
            tags=tags if tags else None,
            created_by_id=current_user.id
        )
        
        if asset_type == 'link':
            # Handle link
            link_url = request.form.get('link_url', '').strip()
            if not link_url:
                return jsonify({'success': False, 'error': 'Link URL is required'}), 400
            
            # Add https:// if no protocol specified
            if not link_url.startswith(('http://', 'https://')):
                link_url = 'https://' + link_url
            
            asset.link_url = link_url
            
        elif asset_type == 'file':
            # Handle file upload
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file provided'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No file selected'}), 400
            
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'File type not allowed'}), 400
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE:
                return jsonify({'success': False, 'error': 'File size exceeds 50MB limit'}), 400
            
            # Secure filename and save
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads', 'company_assets')
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            
            # Store relative path
            asset.file_path = f"uploads/company_assets/{unique_filename}"
            asset.file_name = filename
            asset.file_type = file.content_type
            asset.file_size = file_size
        
        # Save to database
        db.session.add(asset)
        db.session.commit()
        
        # Refresh to load relationships
        db.session.refresh(asset)
        
        logger.info(f"Company asset created: {title} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Asset created successfully',
            'asset': asset.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error creating company asset: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_assets_bp.route('/api/company-assets/<int:asset_id>', methods=['PUT'])
@login_required
def update_asset(asset_id):
    """Update an existing company asset"""
    try:
        asset = CompanyAsset.query.get_or_404(asset_id)
        
        # Update fields
        if 'title' in request.json:
            asset.title = request.json['title']
        if 'description' in request.json:
            asset.description = request.json['description']
        if 'category' in request.json:
            asset.category = request.json['category']
        if 'tags' in request.json:
            asset.tags = request.json['tags']
        if 'is_pinned' in request.json:
            asset.is_pinned = request.json['is_pinned']
        if 'link_url' in request.json and asset.asset_type == 'link':
            asset.link_url = request.json['link_url']
        
        db.session.commit()
        
        logger.info(f"Company asset updated: {asset.title} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Asset updated successfully',
            'asset': asset.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating company asset: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_assets_bp.route('/api/company-assets/<int:asset_id>', methods=['DELETE'])
@login_required
def delete_asset(asset_id):
    """Delete a company asset"""
    try:
        asset = CompanyAsset.query.get_or_404(asset_id)
        
        # Delete file from filesystem if it's a file asset
        if asset.asset_type == 'file' and asset.file_path:
            try:
                file_path = os.path.join(os.path.dirname(__file__), '..', 'static', asset.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not delete file {asset.file_path}: {e}")
        
        # Delete from database
        db.session.delete(asset)
        db.session.commit()
        
        logger.info(f"Company asset deleted: {asset.title} by {current_user.username}")
        
        return jsonify({'success': True, 'message': 'Asset deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting company asset: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_assets_bp.route('/api/company-assets/<int:asset_id>/download')
@login_required
def download_asset(asset_id):
    """Download a file asset"""
    try:
        asset = CompanyAsset.query.get_or_404(asset_id)
        
        if asset.asset_type != 'file' or not asset.file_path:
            return jsonify({'success': False, 'error': 'Asset is not a downloadable file'}), 400
        
        file_path = os.path.join(os.path.dirname(__file__), '..', 'static', asset.file_path)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=asset.file_name
        )
        
    except Exception as e:
        logger.error(f"Error downloading asset: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@company_assets_bp.route('/api/company-assets/<int:asset_id>/toggle-pin', methods=['POST'])
@login_required
def toggle_pin(asset_id):
    """Toggle pin status of an asset"""
    try:
        asset = CompanyAsset.query.get_or_404(asset_id)
        asset.is_pinned = not asset.is_pinned
        db.session.commit()
        
        logger.info(f"Asset pin toggled: {asset.title} - pinned: {asset.is_pinned}")
        
        return jsonify({
            'success': True,
            'is_pinned': asset.is_pinned,
            'message': f"Asset {'pinned' if asset.is_pinned else 'unpinned'} successfully"
        })
        
    except Exception as e:
        logger.error(f"Error toggling pin: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

