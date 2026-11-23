# SPDX-License-Identifier: MIT
# The lab's exact solver and nothing else. The build context is solver/ (see
# wrangler.jsonc), and ../.dockerignore lets only solve.py into it.
# The OR-tools version is the one ceiling.py pins; test.mjs fails if they part.
FROM python:3.13-slim
RUN pip install --no-cache-dir ortools==9.15.6755
COPY solve.py /app/solve.py
# No server inside: the Durable Object runs solve.py once per question, so the
# container only has to stay up.
ENTRYPOINT ["sleep", "infinity"]
