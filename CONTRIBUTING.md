# Contributing

Contributions are welcome, especially around:

- evaluating classification quality;
- improving structured JSON extraction;
- measuring local inference cost and latency;
- anonymizing and protecting Jira data;
- generalizing the pipeline to other operational datasets.

Before proposing a change:

1. verify that Jira data and secrets remain outside the repository;
2. describe the expected behavior clearly;
3. run `python -m compileall -q app.py main.py src`;
4. update the documentation when visible behavior changes.

Model outputs must be presented as verifiable hypotheses, never as confirmed causes without human validation.

