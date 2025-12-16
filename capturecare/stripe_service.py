import os
import stripe
from datetime import datetime, timedelta
from .models import db, Invoice, InvoiceItem, Patient
import logging

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

class StripeService:
    """Service for handling Stripe payments and invoicing"""
    
    @staticmethod
    def get_domain():
        """Get the current domain for Stripe redirects"""
        if os.environ.get('REPLIT_DEPLOYMENT'):
            return os.environ.get('REPLIT_DEV_DOMAIN')
        else:
            domains = os.environ.get('REPLIT_DOMAINS', '').split(',')
            return domains[0] if domains else 'localhost:5000'
    
    @staticmethod
    def generate_invoice_number():
        """Generate unique invoice number"""
        last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
        if last_invoice:
            try:
                last_num = int(last_invoice.invoice_number.split('-')[1])
                return f"INV-{last_num + 1:05d}"
            except:
                pass
        return f"INV-{1:05d}"
    
    @staticmethod
    def get_or_create_customer(patient):
        """Get existing Stripe customer or create new one for patient"""
        if patient.stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(patient.stripe_customer_id)
                logger.info(f"Retrieved existing Stripe customer {customer.id} for patient {patient.id}")
                return customer
            except stripe.error.InvalidRequestError:
                logger.warning(f"Stripe customer {patient.stripe_customer_id} not found, creating new one")
        
        customer = stripe.Customer.create(
            email=patient.email,
            name=f"{patient.first_name} {patient.last_name}",
            metadata={
                'patient_id': patient.id,
                'phone': patient.mobile or patient.phone or ''
            }
        )
        
        patient.stripe_customer_id = customer.id
        db.session.commit()
        logger.info(f"Created new Stripe customer {customer.id} for patient {patient.id}")
        return customer
    
    @staticmethod
    def create_one_off_invoice(patient_id, items, description=None, notes=None, due_days=14):
        """
        Create a one-off invoice for a patient
        
        Args:
            patient_id: Patient ID
            items: List of dicts with 'description', 'quantity', 'unit_price', 'tax_rate'
            description: Invoice description
            notes: Additional notes
            due_days: Days until due (default 14)
        
        Returns:
            Invoice object with Stripe hosted URL
        """
        try:
            patient = Patient.query.get(patient_id)
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")
            
            # Get or create customer in Stripe
            stripe_customer = StripeService.get_or_create_customer(patient)
            
            # Calculate totals
            subtotal = 0
            tax_amount = 0
            line_items = []
            
            for item in items:
                qty = item.get('quantity', 1)
                price = item.get('unit_price', 0)
                tax_rate = item.get('tax_rate', 10.0)  # Default 10% GST
                
                item_subtotal = qty * price
                item_tax = item_subtotal * (tax_rate / 100)
                
                subtotal += item_subtotal
                tax_amount += item_tax
                
                # Create Stripe invoice item
                line_items.append({
                    'price_data': {
                        'currency': 'aud',
                        'product_data': {
                            'name': item.get('description', 'Service'),
                        },
                        'unit_amount': int(price * 100),  # Convert to cents
                    },
                    'quantity': qty,
                    'tax_rates': []  # Tax is included in calculation
                })
            
            total_amount = subtotal + tax_amount
            
            # Create Stripe invoice
            stripe_invoice = stripe.Invoice.create(
                customer=stripe_customer.id,
                auto_advance=False,  # Don't auto-finalize
                collection_method='send_invoice',
                days_until_due=due_days,
                description=description or f"Invoice for {patient.first_name} {patient.last_name}",
                metadata={
                    'patient_id': patient_id,
                    'invoice_type': 'one_off'
                }
            )
            
            # Add line items to invoice
            for item_data in items:
                stripe.InvoiceItem.create(
                    customer=stripe_customer.id,
                    invoice=stripe_invoice.id,
                    currency='aud',
                    amount=int((item_data.get('quantity', 1) * item_data.get('unit_price', 0) * 
                               (1 + item_data.get('tax_rate', 10.0) / 100)) * 100),  # Total with tax in cents
                    description=item_data.get('description', 'Service')
                )
            
            # Finalize the invoice
            stripe_invoice = stripe.Invoice.finalize_invoice(stripe_invoice.id)
            
            # Create local invoice record
            invoice_number = StripeService.generate_invoice_number()
            invoice = Invoice(
                patient_id=patient_id,
                invoice_number=invoice_number,
                invoice_type='one_off',
                status='sent',
                subtotal=subtotal,
                tax_amount=tax_amount,
                total_amount=total_amount,
                currency='AUD',
                invoice_date=datetime.utcnow().date(),
                due_date=(datetime.utcnow() + timedelta(days=due_days)).date(),
                stripe_invoice_id=stripe_invoice.id,
                stripe_hosted_invoice_url=stripe_invoice.hosted_invoice_url,
                stripe_invoice_pdf=stripe_invoice.invoice_pdf,
                description=description,
                notes=notes,
                is_recurring=False
            )
            
            db.session.add(invoice)
            
            # Add invoice items
            for item_data in items:
                qty = item_data.get('quantity', 1)
                price = item_data.get('unit_price', 0)
                tax_rate = item_data.get('tax_rate', 10.0)
                amount = qty * price * (1 + tax_rate / 100)
                
                invoice_item = InvoiceItem(
                    invoice=invoice,
                    description=item_data.get('description', 'Service'),
                    quantity=qty,
                    unit_price=price,
                    tax_rate=tax_rate,
                    amount=amount,
                    item_type=item_data.get('item_type', 'service')
                )
                db.session.add(invoice_item)
            
            db.session.commit()
            
            logger.info(f"✅ Created one-off invoice {invoice_number} for patient {patient_id}")
            return invoice
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error creating one-off invoice: {str(e)}")
            raise
    
    @staticmethod
    def create_recurring_invoice(patient_id, items, frequency='monthly', start_date=None, 
                                 end_date=None, description=None, notes=None):
        """
        Create a recurring subscription invoice for a patient
        
        Args:
            patient_id: Patient ID
            items: List of dicts with 'description', 'quantity', 'unit_price', 'tax_rate'
            frequency: 'weekly', 'monthly', 'quarterly', 'yearly'
            start_date: When to start billing (default: today)
            end_date: When to stop billing (optional)
            description: Invoice description
            notes: Additional notes
        
        Returns:
            Invoice object with Stripe subscription
        """
        try:
            patient = Patient.query.get(patient_id)
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")
            
            # Get or create customer in Stripe
            stripe_customer = StripeService.get_or_create_customer(patient)
            
            # Map frequency to Stripe interval
            interval_mapping = {
                'weekly': 'week',
                'monthly': 'month',
                'quarterly': 'month',
                'yearly': 'year'
            }
            
            interval = interval_mapping.get(frequency, 'month')
            interval_count = 3 if frequency == 'quarterly' else 1
            
            # Calculate totals
            subtotal = 0
            tax_amount = 0
            
            for item in items:
                qty = item.get('quantity', 1)
                price = item.get('unit_price', 0)
                tax_rate = item.get('tax_rate', 10.0)
                
                item_subtotal = qty * price
                item_tax = item_subtotal * (tax_rate / 100)
                
                subtotal += item_subtotal
                tax_amount += item_tax
            
            total_amount = subtotal + tax_amount
            
            # Create Stripe product and price
            stripe_product = stripe.Product.create(
                name=description or f"Recurring Service - {patient.first_name} {patient.last_name}",
                metadata={
                    'patient_id': patient_id
                }
            )
            
            stripe_price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=int(total_amount * 100),  # Convert to cents
                currency='aud',
                recurring={
                    'interval': interval,
                    'interval_count': interval_count
                }
            )
            
            # Create subscription
            subscription_params = {
                'customer': stripe_customer.id,
                'items': [{'price': stripe_price.id}],
                'metadata': {
                    'patient_id': patient_id,
                    'invoice_type': 'recurring'
                },
                'collection_method': 'send_invoice',
                'days_until_due': 14
            }
            
            if start_date:
                # Convert date to datetime (at midnight) before calling timestamp()
                from datetime import datetime as dt
                start_datetime = dt.combine(start_date, dt.min.time())
                subscription_params['billing_cycle_anchor'] = int(start_datetime.timestamp())
            
            stripe_subscription = stripe.Subscription.create(**subscription_params)
            
            # Create local invoice record
            invoice_number = StripeService.generate_invoice_number()
            start = start_date or datetime.utcnow().date()
            
            invoice = Invoice(
                patient_id=patient_id,
                invoice_number=invoice_number,
                invoice_type='recurring',
                status='active',
                subtotal=subtotal,
                tax_amount=tax_amount,
                total_amount=total_amount,
                currency='AUD',
                invoice_date=start,
                stripe_subscription_id=stripe_subscription.id,
                description=description,
                notes=notes,
                is_recurring=True,
                recurring_frequency=frequency,
                recurring_start_date=start,
                recurring_end_date=end_date,
                next_billing_date=start
            )
            
            db.session.add(invoice)
            
            # Add invoice items
            for item_data in items:
                qty = item_data.get('quantity', 1)
                price = item_data.get('unit_price', 0)
                tax_rate = item_data.get('tax_rate', 10.0)
                amount = qty * price * (1 + tax_rate / 100)
                
                invoice_item = InvoiceItem(
                    invoice=invoice,
                    description=item_data.get('description', 'Service'),
                    quantity=qty,
                    unit_price=price,
                    tax_rate=tax_rate,
                    amount=amount,
                    item_type=item_data.get('item_type', 'service')
                )
                db.session.add(invoice_item)
            
            db.session.commit()
            
            logger.info(f"✅ Created recurring invoice {invoice_number} for patient {patient_id}")
            return invoice
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error creating recurring invoice: {str(e)}")
            raise
    
    @staticmethod
    def cancel_subscription(invoice_id):
        """Cancel a recurring subscription"""
        try:
            invoice = Invoice.query.get(invoice_id)
            if not invoice or not invoice.stripe_subscription_id:
                raise ValueError("Invoice not found or not a subscription")
            
            # Cancel in Stripe
            stripe.Subscription.delete(invoice.stripe_subscription_id)
            
            # Update local record
            invoice.status = 'cancelled'
            db.session.commit()
            
            logger.info(f"✅ Cancelled subscription for invoice {invoice.invoice_number}")
            return invoice
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error cancelling subscription: {str(e)}")
            raise
    
    @staticmethod
    def sync_invoice_status(invoice_id):
        """Sync invoice status from Stripe"""
        try:
            invoice = Invoice.query.get(invoice_id)
            if not invoice:
                raise ValueError("Invoice not found")
            
            if invoice.stripe_invoice_id:
                stripe_invoice = stripe.Invoice.retrieve(invoice.stripe_invoice_id)
                
                # Update status
                if stripe_invoice.status == 'paid':
                    invoice.status = 'paid'
                    invoice.paid_date = datetime.fromtimestamp(stripe_invoice.status_transitions.paid_at).date()
                    invoice.amount_paid = stripe_invoice.amount_paid / 100
                elif stripe_invoice.status == 'open':
                    invoice.status = 'sent'
                elif stripe_invoice.status == 'void':
                    invoice.status = 'cancelled'
                
                db.session.commit()
                logger.info(f"✅ Synced invoice {invoice.invoice_number} status: {invoice.status}")
            
            return invoice
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error syncing invoice status: {str(e)}")
            raise
