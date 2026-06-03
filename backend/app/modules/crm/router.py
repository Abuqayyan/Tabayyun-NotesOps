"""CRM aggregator router — mounts every CRM sub-router under one include in main.py.

Note: timeline/linking endpoints use the SINGULAR entity_type in the path
(company|contact|lead|opportunity), e.g. GET /crm/company/{id}/timeline. The list/CRUD
collections are plural (/crm/companies, /crm/contacts, /crm/leads, /crm/opportunities).
"""
from fastapi import APIRouter

from app.modules.crm.companies import router as companies_router
from app.modules.crm.contacts import router as contacts_router
from app.modules.crm.leads import router as leads_router
from app.modules.crm.opportunities import router as opportunities_router
from app.modules.crm.timeline import router as timeline_router
from app.modules.crm.dashboards import router as dashboards_router
from app.modules.crm.intelligence import router as intelligence_router

router = APIRouter()
for _r in (companies_router, contacts_router, leads_router, opportunities_router,
           dashboards_router, intelligence_router, timeline_router):
    router.include_router(_r)
