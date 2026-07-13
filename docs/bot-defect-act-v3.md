# Telegram defect act V3

## Goal

The bot produces a short customer-facing defect act from a nameplate and field comments. DeepSeek classifies facts; local templates own the final wording.

## Document structure

1. Equipment: `Кондиционер <brand> <model>`.
2. Performed: one controlled diagnostic-work sentence.
3. Detected: one diagnosis sentence plus up to three explicitly stated facts.
4. Conclusion: repair, additional diagnostics, or decommissioning/write-off.

Raw technician comments remain in order history but are not copied into the document verbatim.

## Controlled write-off profiles

- `compressor_short_circuit`: short circuit in compressor windings.
- `compressor_winding_open`: open compressor winding.
- `compressor_mechanical_failure`: mechanical failure, seizure, abnormal noise, or no pressure differential.
- `heat_exchanger_multiple_leaks`: multiple through-corrosion points and recurring heat-exchanger leaks.

The last profile uses the engineering term "multiple corrosion perforation". It explains why local brazing cannot restore reliable tightness.

## AI boundary

DeepSeek may return only:

- a known `fault_type`;
- controlled `inspection_codes`;
- up to three `confirmed_facts` copied from input meaning;
- structured operation and decision codes.

It must not generate document prose, measurements, serial numbers, dates, or completed checks that are absent from the input. Temperature is kept low; local templates force the write-off decision for the four exact profiles.

## Extension rule

Add a new diagnosis in three places:

1. Backend profile in `RepairDefectTemplateService.TEMPLATES`.
2. Classification guidance in `DefectActAIService.build_prompt`.
3. Manager option or Telegram preset only when staff need a direct control for it.

Keep generic `compressor_failure`, `heat_exchanger_damage`, and `unknown_fault` as fallbacks when the subtype is not confirmed.
