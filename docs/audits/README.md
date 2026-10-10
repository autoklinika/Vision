# Audyt stanowiska Vision

Skrypt `scripts/audit/vision_audit_v1.sh` wykonuje **wyłącznie operacje odczytu**. Nie instaluje pakietów, nie wymaga `sudo`, nie uruchamia kamer ani napędów i nie pobiera informacji uwierzytelniających.

Na VENTUNO (lokalny terminal VS Code / SSH):

```bash
cd /home/arduino/Vision
bash -n scripts/audit/vision_audit_v1.sh
bash scripts/audit/vision_audit_v1.sh | tee /home/arduino/vision_audit_report.txt
```

**Nie commitować surowego raportu do publicznego repozytorium.** Najpierw przeanalizować zawartość, a dopiero potem utworzyć syntetyczny, pozbawiony identyfikatorów dokument wynikowy.

Zakres: OS, kernel, CPU, RAM, nośniki, stany usług, interfejsy /dev dla kamery/akceleratorów, bibliotek i pakietów. Wykrycie biblioteki QNN czy urządzenia /dev nie jest dowodem skutecznej inferencji. Wykrycie V4L2 nie potwierdza możliwości wyzwalania migawki Sony.

Plan interpretacji: uzupełnić tabelę PASS / FAIL / DO WERYFIKACJI, następnie wykonać osobne testy funkcjonalne GPU/NPU i aparatu.
