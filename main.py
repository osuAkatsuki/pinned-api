#!/usr/bin/env python3.9
from fastapi import FastAPI

import uvicorn
import uvloop

import services

uvloop.install()

def init_api() -> FastAPI:
    app = FastAPI()

    @app.on_event("startup")
    async def startup() -> None:
        await services.db.connect()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await services.db.disconnect()

    import router
    app.include_router(router.router)

    return app

app = init_api()

if __name__ == "__main__":
    uvicorn.run(app, port=9235)
