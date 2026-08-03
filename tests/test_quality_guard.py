from app.orchestration.quality import inspect_response


def test_normal_answer_is_accepted():
    result = inspect_response(
        "Swapping, işletim sisteminin bellekteki süreç veya sayfaları "
        "geçici olarak diske taşımasıdır. RAM gerektiğinde geri alınırlar."
    )
    assert result.accepted is True


def test_repeated_paragraph_loop_is_rejected():
    paragraph = (
        "Swapping, RAM'deki verilerin geçici olarak diske taşınmasıdır. "
        "Bu işlem bellekte yer açar."
    )
    result = inspect_response("\n\n".join([paragraph] * 8))
    assert result.accepted is False


def test_repeated_sentence_loop_is_rejected():
    sentence = "Sistem veriyi disk alanına taşır."
    result = inspect_response(" ".join([sentence] * 12))
    assert result.accepted is False


def test_repeated_code_declarations_are_not_mistaken_for_prose_loop():
    styles = "\n".join(
        f""".panel-{index} {{
  display: flex;
  justify-content: center;
  align-items: center;
}}"""
        for index in range(8)
    )

    result = inspect_response(
        '<<<ADAM_FILE path="styles.css">>>\n'
        + styles
        + "\n<<<ADAM_FILE_END>>>"
    )

    assert result.accepted is True
