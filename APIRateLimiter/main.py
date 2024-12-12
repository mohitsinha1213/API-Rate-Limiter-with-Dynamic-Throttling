from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import aioredis
import time
import json
from typing import Optional

app = FastAPI()

# Initialize a Redis connection pool
redis = None

@app.on_event("startup")
async def startup():
    global redis
    # Connect to Redis
    redis = await aioredis.create_redis_pool('redis://localhost:6379')

@app.on_event("shutdown")
async def shutdown():
    global redis
    # Close Redis connection
    redis.close()
    await redis.wait_closed()

# Basic route to test the app
@app.get("/")
async def read_root():
    return {"message": "Welcome to the API Rate Limiter"}


# Token Bucket parameters
REQUEST_LIMIT = 100  # Max requests per hour
REFILL_RATE = 1  # Tokens replenished per second
WINDOW_SIZE = 3600  # 1 hour in seconds


class RequestData(BaseModel):
    user_id: int
    endpoint: str


async def get_rate_limit_key(user_id: int, endpoint: str):
    """Generate a unique Redis key for each user's rate limit."""
    return f"rate_limit:{user_id}:{endpoint}"


async def check_rate_limit(user_id: int, endpoint: str):
    """Check and enforce rate limit for each user and endpoint."""
    key = await get_rate_limit_key(user_id, endpoint)
    current_time = int(time.time())

    # Get current rate limit data from Redis
    rate_limit_data = await redis.get(key)

    if rate_limit_data:
        rate_limit_data = json.loads(rate_limit_data)
    else:
        rate_limit_data = {"tokens": REQUEST_LIMIT, "timestamp": current_time}

    # Calculate tokens based on the time since last request
    time_diff = current_time - rate_limit_data["timestamp"]
    tokens_to_add = time_diff * REFILL_RATE
    new_tokens = min(rate_limit_data["tokens"] + tokens_to_add, REQUEST_LIMIT)

    if new_tokens > 0:
        # Decrease token count by 1 for this request
        await redis.set(key, json.dumps({"tokens": new_tokens - 1, "timestamp": current_time}), ex=WINDOW_SIZE)
        return True
    else:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


@app.post("/some_endpoint")
async def some_endpoint(data: RequestData):
    """A protected API route with rate limiting."""
    user_id = data.user_id
    endpoint = data.endpoint

    # Check if the user has exceeded their rate limit
    await check_rate_limit(user_id, endpoint)

    return {"message": "Request processed successfully."}


# Define user tiers with different rate limits
USER_TIERS = {
    "free": {"limit": 100, "refill_rate": 1},  # 100 requests per hour
    "premium": {"limit": 1000, "refill_rate": 2},  # 1000 requests per hour
}


async def check_rate_limit(user_id: int, endpoint: str, user_tier: str = "free"):
    """Check if a user has exceeded their rate limit based on their tier."""
    # Fetch tier-specific limits
    tier_limits = USER_TIERS.get(user_tier, USER_TIERS["free"])
    REQUEST_LIMIT = tier_limits["limit"]
    REFILL_RATE = tier_limits["refill_rate"]

    key = await get_rate_limit_key(user_id, endpoint)
    current_time = int(time.time())

    rate_limit_data = await redis.get(key)

    if rate_limit_data:
        rate_limit_data = json.loads(rate_limit_data)
    else:
        rate_limit_data = {"tokens": REQUEST_LIMIT, "timestamp": current_time}

    time_diff = current_time - rate_limit_data["timestamp"]
    tokens_to_add = time_diff * REFILL_RATE
    new_tokens = min(rate_limit_data["tokens"] + tokens_to_add, REQUEST_LIMIT)

    if new_tokens > 0:
        await redis.set(key, json.dumps({"tokens": new_tokens - 1, "timestamp": current_time}), ex=WINDOW_SIZE)
        return True
    else:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")


@app.post("/some_endpoint")
async def some_endpoint(data: RequestData, user_tier: str = "free"):
    """A protected API route with rate limiting based on user tier."""
    user_id = data.user_id
    endpoint = data.endpoint

    # Apply rate limiting based on the user tier
    await check_rate_limit(user_id, endpoint, user_tier)

    return {"message": "Request processed successfully."}
