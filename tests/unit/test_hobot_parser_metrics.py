from parsers.hobot import HobotParser


def test_hobot_extract_metrics_treats_est_as_inverter_true():
    metrics = HobotParser._extract_metrics(
        {
            "Инверторное управление мощностью": "Есть",
            "Мощность охлаждения, кВт": "2.80",
            "Мощность обогрева, кВт": "3.63",
        },
        "Test title",
    )

    assert metrics["is_inverter"] is True
    assert metrics["power_cooling"] == 2.8
    assert metrics["power_heating"] == 3.63
