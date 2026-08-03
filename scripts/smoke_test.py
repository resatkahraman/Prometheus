import asyncio
import json
import os

import httpx


async def main() -> None:
    payload = {
        "message": "Python'da güvenli hata yönetimini üç maddede açıkla.",
        "mode": "economy",
    }

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            os.getenv(
                "ORCHESTRA_URL",
                "http://127.0.0.1:8000/v1/orchestrate",
            ),
            json=payload,
        )

    print("HTTP", response.status_code)
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
