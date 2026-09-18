"""Kuyruk uç noktaları — kuyruk öğesini çalışana atama (PRD 08.2.1; K16, §20.6).

`POST /api/queue/{queue_item_id}/assign` öğeyi gövdedeki çalışana atar ve çıktısını yapay zekâ
çağırmadan üretir (`app.pipeline.route.assign_queue_item`); yapay zekâ sağlayıcısı bu uç noktanın
bağımlılıkları arasında yoktur. İş tek işlemde yapılır: hata olursa hiçbir şey commit edilmez.
Kuyruk öğesi ya da çalışan yoksa 404; öğe atanamıyorsa (çözülmüş, eski sürüm, türsüz, fiziksel
kural reddi, plan ya da Inbox değişmiş) 409 ve nedeni.

K16: manuel işlem iki aşamalı onay ister ve kullanıcı adıyla loglanır. Onaylanmış kullanıcının adı
`get_confirmed_actor` bağımlılığıdır; oturum (10.1.2) ve onay belirteci (10.8.1, §20.6.1) kurulana
kadar 503 döner — onaysız atama yapılmaz.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_session
from app.pipeline.plan import PlanIntegrityError
from app.pipeline.route import (
    AssigneeNotFoundError,
    QueueAssignmentError,
    QueueItemNotFoundError,
    QueueItemReferenceError,
    QueueSourceIntegrityError,
    assign_queue_item,
)
from app.storage import DataLayout
from app.web.routers.uploads import get_layout

router = APIRouter(prefix="/api/queue", tags=["queue"])


class QueueAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str


class QueueAssignmentResponse(BaseModel):
    queue_item_id: int
    upload_id: str
    plan_id: int
    plan_item_id: str
    kind: str
    employee_id: str
    document_id: int
    document_type_slug: str
    operation: str
    resolved_at: datetime
    resolved_by: str


def get_confirmed_actor() -> str:
    """K16: iki aşamalı onayı (§20.6.1) tamamlamış kullanıcının adı.

    Oturum (10.1.2) ve onay belirteci (10.8.1) henüz kurulmadı; manuel işlem onaysız yapılmaz: 503.
    10.8.1 bu bağımlılığı belirteci doğrulayıp tüketen, `USER_CONFIRMED`'ı yazan ve kullanıcı adını
    döndüren hâliyle bağlar.
    """
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "İki aşamalı onay mekanizması henüz kurulmadı; manuel işlem yapılamaz.",
    )


@router.post("/{queue_item_id}/assign", response_model=QueueAssignmentResponse)
def assign_queue_item_to_employee(
    queue_item_id: int,
    request: QueueAssignmentRequest,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[str, Depends(get_confirmed_actor)],
) -> QueueAssignmentResponse:
    """08.2.1 — kuyruk öğesini çalışana atar; çıktı üretilir, yapay zekâ çağrılmaz."""
    try:
        assigned = assign_queue_item(
            session,
            layout,
            queue_item_id,
            request.employee_id,
            actor=actor,
            render_image_dpi=settings.render_image_dpi,
            render_image_jpeg_quality=settings.render_image_jpeg_quality,
        )
    except (QueueItemNotFoundError, AssigneeNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except (
        QueueAssignmentError,
        PlanIntegrityError,
        QueueItemReferenceError,
        QueueSourceIntegrityError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    queue_item, document = assigned.queue_item, assigned.executed.document
    assert queue_item.plan_id is not None and queue_item.plan_item_id is not None
    assert queue_item.resolved_at is not None and queue_item.resolved_by is not None
    return QueueAssignmentResponse(
        queue_item_id=queue_item.id,
        upload_id=queue_item.upload_id,
        plan_id=queue_item.plan_id,
        plan_item_id=queue_item.plan_item_id,
        kind=queue_item.kind,
        employee_id=document.employee_id,
        document_id=document.id,
        document_type_slug=document.type_slug,
        operation=assigned.operation.value,
        resolved_at=queue_item.resolved_at,
        resolved_by=queue_item.resolved_by,
    )
