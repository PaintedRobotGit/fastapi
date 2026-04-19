"""
Customer profile endpoints — brand, services, contacts, documents.

All routes are nested under /customers/{customer_id}/ and enforce
the same access rules as the customers router: admins see everything,
partner users see their own customers, customer-tier users see only
their own record (read-only for most sub-resources).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access import AccessContext, effective_partner_id, ensure_customer_resource, get_access_context
from database import get_db
from models import (
    BrandVoice,
    BrandVoiceInput,
    Customer,
    CustomerContact,
    CustomerDocument,
    CustomerServiceChannel,
    CustomerServices,
    InfoBaseEntry,
    ProductOrService,
    TargetAudience,
)
from schemas import (
    BrandVoiceInputCreate,
    BrandVoiceInputRead,
    BrandVoiceRead,
    BrandVoiceUpdate,
    CustomerContactCreate,
    CustomerContactRead,
    CustomerContactUpdate,
    CustomerDocumentCreate,
    CustomerDocumentRead,
    CustomerDocumentUpdate,
    CustomerServiceChannelCreate,
    CustomerServiceChannelRead,
    CustomerServiceChannelUpdate,
    CustomerServicesRead,
    CustomerServicesUpdate,
    InfoBaseEntryCreate,
    InfoBaseEntryRead,
    InfoBaseEntryUpdate,
    ProductOrServiceCreate,
    ProductOrServiceRead,
    ProductOrServiceUpdate,
    TargetAudienceCreate,
    TargetAudienceRead,
    TargetAudienceUpdate,
)

router = APIRouter(prefix="/customers/{customer_id}", tags=["customer-profile"])


async def _get_customer(customer_id: int, ctx: AccessContext, db: AsyncSession) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    await ensure_customer_resource(ctx, db, customer)
    return customer


async def _partner_id_for(ctx: AccessContext, db: AsyncSession, customer: Customer) -> int:
    return customer.partner_id


# ── Customer Services (1-1) ───────────────────────────────────────────────────

@router.get("/services", response_model=CustomerServicesRead)
async def get_customer_services(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerServices:
    customer = await _get_customer(customer_id, ctx, db)
    row = (await db.execute(select(CustomerServices).where(CustomerServices.customer_id == customer.id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No services record yet — use PUT to create it.")
    return row


@router.put("/services", response_model=CustomerServicesRead)
async def upsert_customer_services(
    customer_id: int,
    body: CustomerServicesUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerServices:
    customer = await _get_customer(customer_id, ctx, db)
    row = (await db.execute(select(CustomerServices).where(CustomerServices.customer_id == customer.id))).scalar_one_or_none()
    if row is None:
        row = CustomerServices(partner_id=customer.partner_id, customer_id=customer.id)
        db.add(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


# ── Service Channels ──────────────────────────────────────────────────────────

@router.get("/service-channels", response_model=list[CustomerServiceChannelRead])
async def list_service_channels(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerServiceChannel]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(CustomerServiceChannel)
        .where(CustomerServiceChannel.customer_id == customer.id)
        .order_by(CustomerServiceChannel.service_area, CustomerServiceChannel.channel_label)
    )
    return list(result.scalars().all())


@router.post("/service-channels", response_model=CustomerServiceChannelRead, status_code=201)
async def create_service_channel(
    customer_id: int,
    body: CustomerServiceChannelCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerServiceChannel:
    customer = await _get_customer(customer_id, ctx, db)
    channel = CustomerServiceChannel(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.patch("/service-channels/{channel_id}", response_model=CustomerServiceChannelRead)
async def update_service_channel(
    customer_id: int,
    channel_id: int,
    body: CustomerServiceChannelUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerServiceChannel:
    customer = await _get_customer(customer_id, ctx, db)
    channel = await db.get(CustomerServiceChannel, channel_id)
    if channel is None or channel.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Service channel not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/service-channels/{channel_id}", status_code=204)
async def delete_service_channel(
    customer_id: int,
    channel_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    channel = await db.get(CustomerServiceChannel, channel_id)
    if channel is None or channel.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Service channel not found.")
    await db.delete(channel)
    await db.commit()


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/documents", response_model=list[CustomerDocumentRead])
async def list_documents(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerDocument]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(CustomerDocument)
        .where(CustomerDocument.customer_id == customer.id)
        .order_by(CustomerDocument.document_type, CustomerDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/documents", response_model=CustomerDocumentRead, status_code=201)
async def create_document(
    customer_id: int,
    body: CustomerDocumentCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerDocument:
    customer = await _get_customer(customer_id, ctx, db)
    doc = CustomerDocument(
        partner_id=customer.partner_id,
        customer_id=customer.id,
        created_by_user_id=ctx.user.id,
        **body.model_dump(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.patch("/documents/{doc_id}", response_model=CustomerDocumentRead)
async def update_document(
    customer_id: int,
    doc_id: int,
    body: CustomerDocumentUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerDocument:
    customer = await _get_customer(customer_id, ctx, db)
    doc = await db.get(CustomerDocument, doc_id)
    if doc is None or doc.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(doc, field, value)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    customer_id: int,
    doc_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    doc = await db.get(CustomerDocument, doc_id)
    if doc is None or doc.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    await db.delete(doc)
    await db.commit()


# ── Brand Voice (1-1) ─────────────────────────────────────────────────────────

@router.get("/brand-voice", response_model=BrandVoiceRead)
async def get_brand_voice(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BrandVoice:
    customer = await _get_customer(customer_id, ctx, db)
    row = (await db.execute(select(BrandVoice).where(BrandVoice.customer_id == customer.id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No brand voice yet — use PUT to create it.")
    return row


@router.put("/brand-voice", response_model=BrandVoiceRead)
async def upsert_brand_voice(
    customer_id: int,
    body: BrandVoiceUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BrandVoice:
    customer = await _get_customer(customer_id, ctx, db)
    row = (await db.execute(select(BrandVoice).where(BrandVoice.customer_id == customer.id))).scalar_one_or_none()
    if row is None:
        row = BrandVoice(partner_id=customer.partner_id, customer_id=customer.id)
        db.add(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


# ── Brand Voice Inputs ────────────────────────────────────────────────────────

@router.get("/brand-voice/inputs", response_model=list[BrandVoiceInputRead])
async def list_brand_voice_inputs(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[BrandVoiceInput]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(BrandVoiceInput)
        .where(BrandVoiceInput.customer_id == customer.id)
        .order_by(BrandVoiceInput.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/brand-voice/inputs", response_model=BrandVoiceInputRead, status_code=201)
async def create_brand_voice_input(
    customer_id: int,
    body: BrandVoiceInputCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> BrandVoiceInput:
    customer = await _get_customer(customer_id, ctx, db)
    inp = BrandVoiceInput(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(inp)
    await db.commit()
    await db.refresh(inp)
    return inp


@router.delete("/brand-voice/inputs/{input_id}", status_code=204)
async def delete_brand_voice_input(
    customer_id: int,
    input_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    inp = await db.get(BrandVoiceInput, input_id)
    if inp is None or inp.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Brand voice input not found.")
    await db.delete(inp)
    await db.commit()


# ── Target Audiences ──────────────────────────────────────────────────────────

@router.get("/audiences", response_model=list[TargetAudienceRead])
async def list_audiences(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[TargetAudience]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(TargetAudience)
        .where(TargetAudience.customer_id == customer.id)
        .order_by(TargetAudience.rank, TargetAudience.id)
    )
    return list(result.scalars().all())


@router.post("/audiences", response_model=TargetAudienceRead, status_code=201)
async def create_audience(
    customer_id: int,
    body: TargetAudienceCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> TargetAudience:
    customer = await _get_customer(customer_id, ctx, db)
    audience = TargetAudience(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(audience)
    await db.commit()
    await db.refresh(audience)
    return audience


@router.patch("/audiences/{audience_id}", response_model=TargetAudienceRead)
async def update_audience(
    customer_id: int,
    audience_id: int,
    body: TargetAudienceUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> TargetAudience:
    customer = await _get_customer(customer_id, ctx, db)
    audience = await db.get(TargetAudience, audience_id)
    if audience is None or audience.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Audience not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(audience, field, value)
    await db.commit()
    await db.refresh(audience)
    return audience


@router.delete("/audiences/{audience_id}", status_code=204)
async def delete_audience(
    customer_id: int,
    audience_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    audience = await db.get(TargetAudience, audience_id)
    if audience is None or audience.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Audience not found.")
    await db.delete(audience)
    await db.commit()


# ── Info Base ─────────────────────────────────────────────────────────────────

@router.get("/info-base", response_model=list[InfoBaseEntryRead])
async def list_info_base(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[InfoBaseEntry]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(InfoBaseEntry)
        .where(InfoBaseEntry.customer_id == customer.id)
        .order_by(InfoBaseEntry.category.nullslast(), InfoBaseEntry.title)
    )
    return list(result.scalars().all())


@router.post("/info-base", response_model=InfoBaseEntryRead, status_code=201)
async def create_info_base_entry(
    customer_id: int,
    body: InfoBaseEntryCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> InfoBaseEntry:
    customer = await _get_customer(customer_id, ctx, db)
    entry = InfoBaseEntry(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/info-base/{entry_id}", response_model=InfoBaseEntryRead)
async def update_info_base_entry(
    customer_id: int,
    entry_id: int,
    body: InfoBaseEntryUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> InfoBaseEntry:
    customer = await _get_customer(customer_id, ctx, db)
    entry = await db.get(InfoBaseEntry, entry_id)
    if entry is None or entry.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Info base entry not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/info-base/{entry_id}", status_code=204)
async def delete_info_base_entry(
    customer_id: int,
    entry_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    entry = await db.get(InfoBaseEntry, entry_id)
    if entry is None or entry.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Info base entry not found.")
    await db.delete(entry)
    await db.commit()


# ── Products & Services ───────────────────────────────────────────────────────

@router.get("/products", response_model=list[ProductOrServiceRead])
async def list_products(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[ProductOrService]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(ProductOrService)
        .where(ProductOrService.customer_id == customer.id)
        .order_by(ProductOrService.sort_order, ProductOrService.name)
    )
    return list(result.scalars().all())


@router.post("/products", response_model=ProductOrServiceRead, status_code=201)
async def create_product(
    customer_id: int,
    body: ProductOrServiceCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ProductOrService:
    customer = await _get_customer(customer_id, ctx, db)
    product = ProductOrService(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductOrServiceRead)
async def update_product(
    customer_id: int,
    product_id: int,
    body: ProductOrServiceUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> ProductOrService:
    customer = await _get_customer(customer_id, ctx, db)
    product = await db.get(ProductOrService, product_id)
    if product is None or product.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Product/service not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    customer_id: int,
    product_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    product = await db.get(ProductOrService, product_id)
    if product is None or product.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Product/service not found.")
    await db.delete(product)
    await db.commit()


# ── Contacts ──────────────────────────────────────────────────────────────────

@router.get("/contacts", response_model=list[CustomerContactRead])
async def list_contacts(
    customer_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerContact]:
    customer = await _get_customer(customer_id, ctx, db)
    result = await db.execute(
        select(CustomerContact)
        .where(CustomerContact.customer_id == customer.id)
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.full_name)
    )
    return list(result.scalars().all())


@router.post("/contacts", response_model=CustomerContactRead, status_code=201)
async def create_contact(
    customer_id: int,
    body: CustomerContactCreate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerContact:
    customer = await _get_customer(customer_id, ctx, db)
    contact = CustomerContact(partner_id=customer.partner_id, customer_id=customer.id, **body.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.patch("/contacts/{contact_id}", response_model=CustomerContactRead)
async def update_contact(
    customer_id: int,
    contact_id: int,
    body: CustomerContactUpdate,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> CustomerContact:
    customer = await _get_customer(customer_id, ctx, db)
    contact = await db.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Contact not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    customer_id: int,
    contact_id: int,
    ctx: AccessContext = Depends(get_access_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer(customer_id, ctx, db)
    contact = await db.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Contact not found.")
    await db.delete(contact)
    await db.commit()
