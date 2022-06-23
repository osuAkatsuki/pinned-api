from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.param_functions import Query
from fastapi.responses import Response

from datetime import datetime
from typing import Optional

import hashlib

import services

router = APIRouter(prefix="/pinned", tags=["Pinned scores API"])


async def check_token(
    request: Request,
):
    if rt := request.headers.get("X-Ripple-Token"):
        token = rt
    elif tok := request.query_params.get("token"):
        token = tok
    elif k := request.query_params.get("k"):
        token = k
    else:
        token = request.cookies.get("rt")

    if not token:
        print("no token")
        raise HTTPException(status_code=400, detail="No token provided")

    user_id = await services.db.fetch_val(
        "SELECT user FROM tokens WHERE token = :token",
        {"token": hashlib.md5(token.encode()).hexdigest()},
    )

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token")

    return user_id


async def calculate_grade(score) -> None:
    mode = score["play_mode"]
    n300 = score["300_count"]
    n100 = score["100_count"]
    n50 = score["50_count"]
    miss = score["misses_count"]
    katu = score["katus_count"]
    geki = score["gekis_count"]

    if mode == 0:
        hits = n300 + n100 + n50 + miss

        if hits == 0:
            acc = 0.0
            return
        else:
            acc = (
                100.0
                * ((n50 * 50.0) + (n100 * 100.0) + (n300 * 300.0))
                / (hits * 300.0)
            )

    elif mode == 1:
        hits = n300 + n100 + miss

        if hits == 0:
            acc = 0.0
            return
        else:
            acc = 100.0 * ((n100 * 0.5) + n300) / hits
    elif mode == 2:
        hits = n300 + n100 + n50 + katu + miss

        if hits == 0:
            acc = 0.0
            return
        else:
            acc = 100.0 * (n300 + n100 + n50) / hits
    elif mode == 3:
        hits = n300 + n100 + n50 + geki + katu + miss

        if hits == 0:
            acc = 0.0
            return
        else:
            acc = (
                100.0
                * (
                    (n50 * 50.0)
                    + (n100 * 100.0)
                    + (katu * 200.0)
                    + ((n300 + geki) * 300.0)
                )
                / (hits * 300.0)
            )

    return acc


@router.get("/pinned")
async def get_pinned(
    name: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None, alias="id"),
    rx: int = Query(0),
    mode_arg: int = Query(0, alias="mode"),
    page: int = Query(1, alias="p"),
    limit: int = Query(50, alias="l", ge=0, le=100),
):
    if name is not None:
        user_id = await services.db.fetch_val(
            "SELECT id FROM users WHERE username_safe = :name",
            {"name": name.replace(" ", "_").lower()},
        )

    if user_id is None:
        return {
            "code": 404,
            "message": "User not found",
        }

    offset = limit * (page - 1) if page != 1 else 0

    table = "scores"
    if rx == 1:
        table = "scores_relax"
    elif rx == 2:
        table = "scores_ap"

    result = await services.db.fetch_all(
        f"SELECT s.*, beatmaps.max_combo map_combo, s.max_combo score_combo, s.id score_id, beatmaps.* FROM {table} s INNER JOIN beatmaps USING(beatmap_md5) WHERE pinned = 1 AND play_mode = :mode AND userid = :user_id ORDER BY pp DESC LIMIT :offset, :limit",
        {
            "mode": mode_arg,
            "user_id": user_id,
            "offset": offset,
            "limit": limit,
        },
    )

    return {
        "code": 200,
        "scores": [
            {
                "id": s["score_id"],
                "beatmap_md5": s["beatmap_md5"],
                "score": s["score"],
                "max_combo": s["score_combo"],
                "full_combo": bool(s["full_combo"]),
                "mods": s["mods"],
                "count_300": s["300_count"],
                "count_100": s["100_count"],
                "count_50": s["50_count"],
                "count_geki": s["gekis_count"],
                "count_katu": s["katus_count"],
                "count_miss": s["misses_count"],
                "time": datetime.fromtimestamp(s["time"]).isoformat() + "Z",
                "play_mode": s["play_mode"],
                "accuracy": s["accuracy"],
                "pp": s["pp"],
                "rank": await calculate_grade(s),
                "completed": s["completed"],
                "beatmap": {
                    "beatmap_id": s["beatmap_id"],
                    "beatmapset_id": s["beatmapset_id"],
                    "beatmap_md5": s["beatmap_md5"],
                    "song_name": s["song_name"],
                    "ar": s["ar"],
                    "od": s["od"],
                    "difficulty": 0,
                    "difficulty2": {
                        "std": 0,
                        "taiko": 0,
                        "ctb": 0,
                        "mania": 0,
                    },
                    "max_combo": s["map_combo"],
                    "hit_length": s["hit_length"],
                    "ranked": s["ranked"],
                    "ranked_status_freezed": s["ranked_status_freezed"],
                    "latest_update": datetime.fromtimestamp(
                        s["latest_update"]
                    ).isoformat(),
                },
            }
            for s in result
        ],
    }

from pydantic import BaseModel, Field

class PinScoreModel(BaseModel):
    score_id: int = Field(alias="id")
    relax: int = Field(alias="rx", ge=0, le=2) # 0, 1, 2

@router.post("/pin")
async def pin_score(
    form_data: PinScoreModel,
    _ = Depends(check_token),
):
    table = "scores"

    if form_data.relax == 1:
        table = "scores_relax"
    elif form_data.relax == 2:
        table = "scores_ap"

    if not await services.db.fetch_val(
        f"SELECT 1 FROM {table} WHERE id = :id", {"id": form_data.score_id}
    ):
        print(f"couldn't find score id {form_data.score_id} in {table}")

        return Response(
            status_code=400,
            content="I'd also like to pin a score I don't have... but I can't.",
        )
    await services.db.execute(
        f"UPDATE {table} SET pinned = 1 WHERE id = :id", {"id": form_data.score_id}
    )

    print(f"pinned {form_data.score_id} on {table}")
    return {"score_id": form_data.score_id}


@router.post("/unpin")
async def unpin_score(
    form_data: PinScoreModel,
    _=Depends(check_token),
):
    table = "scores"

    if form_data.relax == 1:
        table = "scores_relax"
    elif form_data.relax == 2:
        table = "scores_ap"

    if not await services.db.fetch_val(
        f"SELECT 1 FROM {table} WHERE id = :id", {"id": form_data.score_id}
    ):
        print(f"couldn't find score id {form_data.score_id} in {table}")

        return Response(
            status_code=400,
            content="I'd also like to unpin a score I don't have... but I can't.",
        )

    await services.db.execute(
        f"UPDATE {table} SET pinned = 0 WHERE id = :id", {"id": form_data.score_id}
    )
    return {}
