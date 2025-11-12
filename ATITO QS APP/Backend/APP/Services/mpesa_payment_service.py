# backend/app/services/mpesa_payment_service.py
"""
M-Pesa Payment Service
Daraja API Integration for subscription payments
Author: Eng. STEPHEN ODHIAMBO
"""

import httpx
import base64
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, SubscriptionPlan
import uuid


class MpesaService:
    """
    M-Pesa Daraja API Service
    Handles STK Push and payment callbacks
    """
    
    # Daraja API URLs
    SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
    PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"
    
    def __init__(self, db: Session, use_production: bool = False):
        self.db = db
        self.base_url = self.PRODUCTION_BASE_URL if use_production else self.SANDBOX_BASE_URL
        self.access_token = None
    
    async def get_access_token(self) -> str:
        """
        Get OAuth access token from Daraja API
        """
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        # Create authorization header
        auth_string = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
        auth_bytes = auth_string.encode('ascii')
        auth_base64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            'Authorization': f'Basic {auth_base64}'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                self.access_token = data['access_token']
                return self.access_token
        
        except Exception as e:
            print(f"Error getting M-Pesa access token: {str(e)}")
            raise
    
    def generate_password(self, timestamp: str) -> str:
        """
        Generate password for STK Push
        Password = Base64(Shortcode + Passkey + Timestamp)
        """
        data_to_encode = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        encoded = base64.b64encode(data_to_encode.encode()).decode('utf-8')
        return encoded
    
    async def initiate_stk_push(
        self,
        phone_number: str,
        amount: float,
        account_reference: str,
        transaction_desc: str
    ) -> Dict[str, Any]:
        """
        Initiate STK Push (Lipa Na M-Pesa Online)
        
        Args:
            phone_number: Customer phone number (format: 254XXXXXXXXX)
            amount: Amount to charge
            account_reference: Reference (e.g., subscription plan)
            transaction_desc: Description of transaction
        """
        # Ensure access token
        if not self.access_token:
            await self.get_access_token()
        
        # Generate timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        # Format phone number
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]
        
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone_number,
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                return response.json()
        
        except Exception as e:
            print(f"Error initiating STK Push: {str(e)}")
            raise
    
    async def process_subscription_payment(
        self,
        user: User,
        plan: SubscriptionPlan,
        phone_number: str
    ) -> Dict[str, Any]:
        """
        Process subscription payment
        
        Args:
            user: User making payment
            plan: Subscription plan (PRO or BUSINESS)
            phone_number: M-Pesa phone number
        """
        # Determine amount based on plan
        if plan == SubscriptionPlan.PRO:
            amount = settings.PRO_MONTHLY_COST
            duration = 30
        elif plan == SubscriptionPlan.BUSINESS:
            amount = settings.BUSINESS_MONTHLY_COST
            duration = 30
        else:
            raise ValueError("Invalid subscription plan for payment")
        
        # Create transaction record
        transaction = Transaction(
            user_id=user.id,
            transaction_id=str(uuid.uuid4()),
            phone_number=phone_number,
            amount=amount,
            payment_method="mpesa",
            payment_type="SUBSCRIPTION",
            subscription_plan=plan.value,
            subscription_duration=duration,
            status=TransactionStatus.PENDING
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        # Initiate STK Push
        try:
            result = await self.initiate_stk_push(
                phone_number=phone_number,
                amount=amount,
                account_reference=f"SUB-{plan.value.upper()}",
                transaction_desc=f"ATITO QS {plan.value.upper()} Subscription"
            )
            
            # Update transaction with M-Pesa response
            transaction.callback_data = result
            self.db.commit()
            
            return {
                "success": True,
                "transaction_id": str(transaction.id),
                "mpesa_checkout_request_id": result.get("CheckoutRequestID"),
                "merchant_request_id": result.get("MerchantRequestID"),
                "response_code": result.get("ResponseCode"),
                "response_description": result.get("ResponseDescription"),
                "customer_message": result.get("CustomerMessage")
            }
        
        except Exception as e:
            # Update transaction status
            transaction.status = TransactionStatus.FAILED
            transaction.callback_data = {"error": str(e)}
            self.db.commit()
            
            return {
                "success": False,
                "error": str(e),
                "transaction_id": str(transaction.id)
            }
    
    async def handle_callback(self, callback_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle M-Pesa callback
        Called by Daraja API after payment completion
        """
        try:
            # Extract data from callback
            body = callback_data.get("Body", {})
            stk_callback = body.get("stkCallback", {})
            
            result_code = stk_callback.get("ResultCode")
            result_desc = stk_callback.get("ResultDesc")
            merchant_request_id = stk_callback.get("MerchantRequestID")
            checkout_request_id = stk_callback.get("CheckoutRequestID")
            
            # Extract metadata
            callback_metadata = stk_callback.get("CallbackMetadata", {})
            items = callback_metadata.get("Item", [])
            
            # Parse items
            amount = None
            mpesa_receipt = None
            phone_number = None
            
            for item in items:
                name = item.get("Name")
                value = item.get("Value")
                
                if name == "Amount":
                    amount = value
                elif name == "MpesaReceiptNumber":
                    mpesa_receipt = value
                elif name == "PhoneNumber":
                    phone_number = str(value)
            
            # Find transaction
            transaction = self.db.query(Transaction).filter(
                Transaction.callback_data.contains({"CheckoutRequestID": checkout_request_id})
            ).first()
            
            if not transaction:
                print(f"Transaction not found for checkout request: {checkout_request_id}")
                return {"success": False, "error": "Transaction not found"}
            
            # Update transaction
            if result_code == 0:  # Success
                transaction.status = TransactionStatus.SUCCESS
                transaction.mpesa_receipt_number = mpesa_receipt
                transaction.completed_at = datetime.utcnow()
                
                # Activate subscription
                user = self.db.query(User).filter(User.id == transaction.user_id).first()
                
                if user:
                    user.subscription_plan = SubscriptionPlan(transaction.subscription_plan)
                    user.subscription_active = True
                    user.subscription_start_date = datetime.utcnow()
                    
                    # Calculate end date (30 days from now)
                    from datetime import timedelta
                    user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                
                self.db.commit()
                
                return {
                    "success": True,
                    "transaction_id": str(transaction.id),
                    "status": "completed",
                    "mpesa_receipt": mpesa_receipt
                }
            
            else:  # Failed
                transaction.status = TransactionStatus.FAILED
                transaction.callback_data.update({
                    "result_code": result_code,
                    "result_desc": result_desc
                })
                self.db.commit()
                
                return {
                    "success": False,
                    "transaction_id": str(transaction.id),
                    "status": "failed",
                    "reason": result_desc
                }
        
        except Exception as e:
            print(f"Error handling M-Pesa callback: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def query_transaction_status(self, checkout_request_id: str) -> Dict[str, Any]:
        """
        Query the status of an STK Push transaction
        """
        if not self.access_token:
            await self.get_access_token()
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                return response.json()
        
        except Exception as e:
            print(f"Error querying transaction status: {str(e)}")
            raise


# backend/app/api/payments.py
"""
Payment API Endpoints
Handles M-Pesa payments and subscription management
Author: Eng. STEPHEN ODHIAMBO
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.user import User, SubscriptionPlan
from app.services.payment_service import MpesaService
from app.services.auth_service import get_current_user
from app.models.audit import AuditLog

router = APIRouter(prefix="/api/payments", tags=["Payments"])


class PaymentRequest(BaseModel):
    phone_number: str
    plan: SubscriptionPlan
    

class PaymentResponse(BaseModel):
    success: bool
    transaction_id: Optional[str]
    message: str
    checkout_request_id: Optional[str]


@router.post("/subscribe", response_model=PaymentResponse)
async def initiate_subscription_payment(
    payment_data: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initiate subscription payment via M-Pesa
    
    Plans:
    - PRO: KES 500/month (8 projects/day, 5 floors max)
    - BUSINESS: KES 2000/month (Unlimited projects, 10 floors max)
    """
    # Validate plan
    if payment_data.plan not in [SubscriptionPlan.PRO, SubscriptionPlan.BUSINESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid subscription plan. Choose PRO or BUSINESS."
        )
    
    # Initialize M-Pesa service
    mpesa_service = MpesaService(db, use_production=not settings.DEBUG)
    
    try:
        result = mpesa_service.process_subscription_payment(
            user=current_user,
            plan=payment_data.plan,
            phone_number=payment_data.phone_number
        )
        
        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action_type="PAYMENT_INITIATED",
            resource_type="SUBSCRIPTION",
            description=f"Initiated {payment_data.plan.value} subscription payment",
            metadata=result,
            status="SUCCESS" if result["success"] else "FAILURE"
        )
        db.add(audit)
        db.commit()
        
        if result["success"]:
            return PaymentResponse(
                success=True,
                transaction_id=result["transaction_id"],
                message="Payment request sent. Please enter your M-Pesa PIN on your phone.",
                checkout_request_id=result.get("mpesa_checkout_request_id")
            )
        else:
            return PaymentResponse(
                success=False,
                transaction_id=result.get("transaction_id"),
                message=f"Payment failed: {result.get('error')}",
                checkout_request_id=None
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment processing error: {str(e)}"
        )


@router.post("/callback")
async def mpesa_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    M-Pesa payment callback endpoint
    Called by Daraja API after payment completion
    """
    callback_data = await request.json()
    
    # Process callback
    mpesa_service = MpesaService(db)
    result = mpesa_service.handle_callback(callback_data)
    
    # Log callback
    audit = AuditLog(
        action_type="MPESA_CALLBACK",
        resource_type="PAYMENT",
        description="M-Pesa payment callback received",
        metadata=callback_data,
        status="SUCCESS" if result["success"] else "FAILURE"
    )
    db.add(audit)
    db.commit()
    
    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted"
    }


@router.get("/status/{transaction_id}")
async def check_payment_status(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check status of a payment transaction
    """
    from app.models.transaction import Transaction
    
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id
    ).first()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    return {
        "transaction_id": str(transaction.id),
        "status": transaction.status.value,
        "amount": transaction.amount,
        "mpesa_receipt": transaction.mpesa_receipt_number,
        "created_at": transaction.initiated_at,
        "completed_at": transaction.completed_at
    }


@router.get("/subscription")
async def get_subscription_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's subscription information
    """
    return {
        "subscription_plan": current_user.subscription_plan.value,
        "is_active": current_user.subscription_active,
        "start_date": current_user.subscription_start_date,
        "end_date": current_user.subscription_end_date,
        "trial_end_date": current_user.trial_end_date if current_user.subscription_plan.value == "free" else None,
        "max_floors": current_user.get_max_floors(),
        "daily_project_limit": settings.PRO_DAILY_PROJECT_LIMIT if current_user.subscription_plan.value == "pro" else None
    }


@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel current subscription
    (User will retain access until end of paid period)
    """
    current_user.subscription_active = False
    db.commit()
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action_type="SUBSCRIPTION_CANCELLED",
        resource_type="SUBSCRIPTION",
        description=f"User cancelled {current_user.subscription_plan.value} subscription",
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": "Subscription cancelled successfully",
        "access_until": current_user.subscription_end_date
    }
