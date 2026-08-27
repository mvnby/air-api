from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Order, OrderDocument
from services.customer_party import is_business_customer_type


@dataclass(frozen=True)
class EmailTemplateOption:
    key: str
    label: str
    requires_documents: bool = True


class OrderEmailTemplateService:
    TEMPLATE_OPTIONS = (
        EmailTemplateOption("auto", "Автоматически"),
        EmailTemplateOption("offer", "Коммерческое предложение"),
        EmailTemplateOption("invoice", "Счёт"),
        EmailTemplateOption("contract", "Договор"),
        EmailTemplateOption("documents", "Комплект документов"),
        EmailTemplateOption("act", "Акт"),
        EmailTemplateOption("request_requisites", "Запросить реквизиты", False),
        EmailTemplateOption("request_signer", "Запросить данные подписанта", False),
        EmailTemplateOption("custom", "Произвольное письмо", False),
    )
    TEMPLATE_KEYS = {item.key for item in TEMPLATE_OPTIONS}

    DOCUMENT_LABELS = {
        "offer": "коммерческое предложение",
        "invoice": "счёт",
        "contract": "договор",
        "retail_receipt": "товарный чек",
        "service_act": "заказ-акт",
        "maintenance_service_act": "заказ-акт на техническое обслуживание",
        "warranty_certificate": "гарантийный талон",
        "act": "акт выполненных работ",
        "defect_act": "дефектный акт",
        "tn2": "товарную накладную ТН-2",
        "ttn1": "товарно-транспортную накладную ТТН-1",
        "uploaded_pdf": "PDF-документ",
    }
    SUBJECT_DOCUMENT_LABELS = {
        "offer": "коммерческое предложение",
        "invoice": "счёт",
        "contract": "договор",
        "retail_receipt": "товарный чек",
        "service_act": "заказ-акт",
        "maintenance_service_act": "заказ-акт на техническое обслуживание",
        "warranty_certificate": "гарантийный талон",
        "act": "акт выполненных работ",
        "defect_act": "дефектный акт",
        "tn2": "ТН-2",
        "ttn1": "ТТН-1",
        "uploaded_pdf": "Документ",
    }

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").split())

    @classmethod
    def _join_labels(cls, labels: Iterable[str]) -> str:
        values = list(dict.fromkeys(label for label in labels if label))
        if not values:
            return "документы"
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} и {values[1]}"
        return ", ".join(values[:-1]) + f" и {values[-1]}"

    @staticmethod
    def _scenario_label(order: Order) -> str:
        workflow = str(getattr(order, "workflow_type", "") or "").strip()
        has_products = bool(getattr(order, "product_links", []))
        has_services = bool(getattr(order, "service_links", []))
        service_titles = " ".join(
            str(getattr(item, "title", "") or "").lower()
            for item in getattr(order, "service_links", [])
        )
        if "диагност" in service_titles:
            return "диагностику оборудования"
        if "обслуж" in service_titles:
            return "техническое обслуживание кондиционеров"
        if "ремонт" in service_titles:
            return "ремонт кондиционеров"
        if "монтаж" in service_titles and not has_products:
            return "монтаж кондиционеров"
        if workflow == "maintenance":
            return "техническое обслуживание кондиционеров"
        if workflow == "repair":
            return "ремонт кондиционеров"
        if workflow == "service_work":
            return "выполнение работ"
        if has_products and has_services:
            return "поставку и монтаж кондиционеров"
        if has_products:
            return "поставку кондиционеров"
        if has_services:
            return "выполнение работ"
        return "заказ"

    @classmethod
    def _missing_requisites(cls, order: Order) -> List[Dict[str, str]]:
        customer = order.customer
        if customer is None:
            return [{"key": "customer", "label": "карточка клиента"}]

        required = [
            ("email", "контактный e-mail", customer.email),
            ("phone", "контактный телефон", customer.phone),
        ]
        if is_business_customer_type(customer.type):
            customer_type = getattr(customer.type, "value", customer.type)
            is_entrepreneur = customer_type == "individual_entrepreneur"
            business_required = [
                (
                    "full_legal_name",
                    "полное наименование ИП" if is_entrepreneur else "полное наименование организации",
                    customer.full_legal_name,
                ),
                ("inn", "УНП", customer.inn),
                (
                    "legal_address",
                    "адрес регистрации" if is_entrepreneur else "юридический адрес",
                    customer.legal_address,
                ),
                ("bank_name", "наименование банка", customer.bank_name),
                ("bic", "BIC банка", customer.bic),
                ("iban", "расчётный счёт IBAN", customer.iban),
                ("signer_name", "ФИО подписанта", customer.signer_name),
            ]
            signs_personally = (
                is_entrepreneur
                and str(customer.signing_mode or "").strip() == "self"
            )
            if not signs_personally:
                business_required.extend(
                    [
                        ("signer_position", "должность подписанта", customer.signer_position),
                        ("acting_basis", "основание полномочий подписанта", customer.acting_basis),
                    ]
                )
            required = [*business_required, *required]
        return [
            {"key": key, "label": label}
            for key, label, value in required
            if not cls._clean(value)
        ]

    @staticmethod
    def _request_body(labels: List[str], *, signer_only: bool = False) -> str:
        if signer_only:
            intro = "Для подготовки договора просим сообщить данные лица, которое будет подписывать договор:"
        else:
            intro = "Для подготовки документов просим дополнительно сообщить:"
        details = [f"- {label};" for label in labels]
        if details:
            details[-1] = details[-1].rstrip(";") + "."
        elif signer_only:
            details = ["- подтвердить актуальность данных подписанта."]
        else:
            details = ["- актуальные реквизиты организации."]
        return "\n".join(
            [
                "Добрый день!",
                "",
                intro,
                "",
                *details,
                "",
                "С уважением,",
                "Мастер Воздуха",
            ]
        )

    @classmethod
    def _select_template(cls, requested: str, document_types: List[str]) -> str:
        if requested != "auto":
            return requested
        unique_types = list(dict.fromkeys(document_types))
        if len(unique_types) > 1:
            return "documents"
        if unique_types:
            doc_type = unique_types[0]
            if doc_type in {"offer", "invoice", "contract"}:
                return doc_type
            if doc_type in {
                "act",
                "service_act",
                "maintenance_service_act",
                "defect_act",
                "retail_receipt",
            }:
                return "act"
        return "documents"

    @classmethod
    async def compose(
        cls,
        session: AsyncSession,
        *,
        order_id: int,
        document_ids: List[int],
        template_key: str = "auto",
    ) -> Dict[str, Any]:
        if template_key not in cls.TEMPLATE_KEYS:
            raise ValueError("Unknown email template")

        order = (
            await session.execute(
                select(Order)
                .where(Order.id == order_id)
                .options(
                    selectinload(Order.customer),
                    selectinload(Order.documents),
                    selectinload(Order.product_links),
                    selectinload(Order.service_links),
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if order is None:
            raise ValueError("Order not found")

        documents_by_id = {int(item.id): item for item in order.documents}
        documents: List[OrderDocument] = []
        for document_id in document_ids:
            document = documents_by_id.get(int(document_id))
            if document is None:
                raise ValueError(f"Document {document_id} not found on order")
            documents.append(document)

        selected_template = cls._select_template(template_key, [item.doc_type for item in documents])
        option = next(item for item in cls.TEMPLATE_OPTIONS if item.key == selected_template)
        if option.requires_documents and not documents:
            raise ValueError("Select at least one document")

        missing = cls._missing_requisites(order)
        signer_keys = {"signer_name", "signer_position", "acting_basis"}
        signer_missing = [item for item in missing if item["key"] in signer_keys]
        scenario = cls._scenario_label(order)

        if selected_template == "request_requisites":
            labels = [item["label"] for item in missing]
            subject = "Запрос реквизитов для подготовки документов"
            body_text = cls._request_body(labels)
        elif selected_template == "request_signer":
            labels = [item["label"] for item in signer_missing]
            subject = "Запрос данных подписанта для договора"
            body_text = cls._request_body(labels, signer_only=True)
        elif selected_template == "custom":
            subject = f"По заказу #{order.id}"
            body_text = "\n".join(["Добрый день!", "", "", "С уважением,", "Мастер Воздуха"])
        else:
            body_labels = [
                cls.DOCUMENT_LABELS.get(item.doc_type, "документ")
                for item in documents
            ]
            subject_labels = [
                cls.SUBJECT_DOCUMENT_LABELS.get(item.doc_type, "Документ")
                for item in documents
            ]
            body_document_label = cls._join_labels(body_labels)
            subject_document_label = cls._join_labels(subject_labels)
            if len(set(item.doc_type for item in documents)) > 2:
                subject_document_label = "Документы"
            elif subject_document_label:
                subject_document_label = subject_document_label[:1].upper() + subject_document_label[1:]
            subject = f"{subject_document_label} на {scenario}"
            body_text = "\n".join(
                [
                    "Добрый день!",
                    "",
                    f"Направляем {body_document_label} на {scenario}.",
                    "Документ приложен к письму." if len(documents) == 1 else "Документы приложены к письму.",
                    "",
                    "С уважением,",
                    "Мастер Воздуха",
                ]
            )

        return {
            "template_key": selected_template,
            "template_options": [
                {
                    "key": item.key,
                    "label": item.label,
                    "requires_documents": item.requires_documents,
                }
                for item in cls.TEMPLATE_OPTIONS
            ],
            "subject": subject,
            "body_text": body_text,
            "document_ids": [int(item.id) for item in documents],
            "document_labels": [
                f"{cls.SUBJECT_DOCUMENT_LABELS.get(item.doc_type, 'Документ')} {item.number}"
                for item in documents
            ],
            "missing_requisites": missing,
        }
