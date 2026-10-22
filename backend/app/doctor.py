import argparse
import sys

import sqlalchemy as sa
from pydantic import ValidationError

from app.config import Settings
from app.llm import ModelRole, complete


def _first_line(error: Exception) -> str:
    return (str(error).splitlines() or [type(error).__name__])[0]


def _env_failure(error: ValidationError) -> str:
    names = ", ".join(str(e["loc"][0]) for e in error.errors())
    return f"{names} invalid or missing"


def main() -> int:
    parser = argparse.ArgumentParser(prog="doctor")
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args()
    lines: list[str] = []
    try:
        settings: Settings | None = Settings()
        lines.append("OK env")
    except ValidationError as error:
        settings = None
        lines.append(f"FAIL env {_env_failure(error)}")

    if settings is None:
        lines.append("FAIL db settings did not load")
        lines.append("FAIL model settings did not load")
    else:
        try:
            engine = sa.create_engine(settings.database_url)
            with engine.connect() as conn:
                conn.execute(sa.text("select 1"))
            lines.append("OK db")
        except Exception as error:
            lines.append(f"FAIL db {_first_line(error)}")
        if args.skip_model:
            lines.append("SKIP model")
        else:
            try:
                result = complete(
                    ModelRole.FAST,
                    [{"role": "user", "content": "ping"}],
                    purpose="doctor",
                    max_tokens=1,
                )
                tokens = result.prompt_tokens + result.completion_tokens
                lines.append(
                    f"OK model {result.model} {tokens} tokens "
                    f"{result.cost_usd:.6f} USD {result.latency_ms} ms"
                )
            except Exception as error:
                lines.append(f"FAIL model {_first_line(error)}")

    print("\n".join(lines))
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
