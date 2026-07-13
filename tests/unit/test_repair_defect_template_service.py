from services.repair_defect_template_service import RepairDefectTemplateService


def test_compressor_short_circuit_builds_compact_write_off_act():
    meta = RepairDefectTemplateService.build_meta_from_structured(
        raw={
            "fault_type": "compressor_short_circuit",
            "repairable": True,
            "confirmed_facts": ["сопротивление между выводами близко к нулю."],
        },
        diagnostic_notes="кз компрессора, автомат выбивает, много разговорных подробностей",
    )

    assert meta["decision"] == "write_off"
    assert meta["repair_possible"] == "Нет"
    assert meta["likely_diagnosis"] == "Короткое замыкание обмоток компрессора"
    assert "измерение сопротивления обмоток компрессора" in meta["inspection_work_done"]
    assert "сопротивление между выводами близко к нулю" in meta["diagnostic_result"]
    assert "подлежит выводу из эксплуатации и списанию" in meta["technical_conclusion"]
    assert "разговорных подробностей" not in meta["inspection_work_done"]
    assert "скрыт" not in meta["technical_conclusion"].lower()


def test_heat_exchanger_multiple_leaks_uses_corrosion_perforation_wording():
    meta = RepairDefectTemplateService.build_meta_from_structured(
        raw={"fault_type": "multiple_heat_exchanger_defects"},
    )

    assert meta["fault_type"] == "heat_exchanger_multiple_leaks"
    assert meta["decision"] == "write_off"
    assert "манометрическая диагностика" in meta["inspection_work_done"]
    assert "множественные очаги сквозной коррозии" in meta["diagnostic_result"].lower()
    assert "локальная пайка" in meta["operation_restrictions"].lower()
    assert "подлежит выводу из эксплуатации и списанию" in meta["recommended_decision"]


def test_repairable_template_keeps_short_repair_decision():
    meta = RepairDefectTemplateService.build_meta_from_structured(
        raw={"fault_type": "drainage_failure"},
    )

    assert meta["decision"] == "repair"
    assert meta["repair_possible"] == "Да"
    assert meta["inspection_work_done"].startswith("Выполнен комплекс диагностических работ:")
    assert meta["technical_conclusion"].startswith("Рекомендуется прочистить дренажную систему")
