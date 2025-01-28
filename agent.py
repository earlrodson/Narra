from __future__ import annotations

import logging
import json
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents.multimodal import MultimodalAgent
from livekit.plugins import openai as livekit_openai

from openai import OpenAI
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from datetime import datetime

import requests
import aiohttp


load_dotenv(dotenv_path=".env.local")
api_key = os.getenv("OPENAI_API_KEY")
POST_TRANSCRIP_URL = os.getenv('BUBBLE_TRANSCRIPT_ENDPOINT')
GET_TRANSCRIPT_URL = os.getenv('BUBBLE_GET_TRANSCRIPT_ENDPOINT')
POST_STORY_URL = os.getenv('BUBBLE_STORY_ENDPOINT')

logger = logging.getLogger("my-worker")
logger.setLevel(logging.INFO)

if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables. Make sure it is set in .env.local.")
OpenAI.api_key = api_key

# Initialize FastAPI
app = FastAPI()

# CORS settings: Allow requests from localhost:4000
origins = [
    "http://localhost:4000",  # Frontend URL
    "*"
]

# Add CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow frontend URL to make requests
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Initialize conversation history globally
conversation_history = []

# FastAPI model for the request to generate story
class TranscriptRequest(BaseModel):
    userRoomId: str
    chapterId: int
    transcript: str
    accountId: int
    timestamp: str

# FastAPI model for the response
class StoryResponse(BaseModel):
    chapterId: int
    story: str
    
class StoryRequest(BaseModel):
    story: str
    
@app.get("/")
async def main():
    try:
        logger.info(f"Welcome to the Narra API")
        return { "message": "Welcome to the Narra API" }    
    except Exception as e:
        # Catch any errors and return the message
        return {"error": str(e)}

@app.post("/transcript/")
async def post_transcript(data: TranscriptRequest):
    try:
        logger.info(f"Passing transcript to bubble")
        
        # Parse the transcript into a list of messages
        transcript_data = json.loads(data.transcript)

        # Format the transcript data
        formattedData = ""
        for entry in transcript_data:
            message = entry["message"].strip()  # Clean up the message
            if entry["isSelf"]:
                # User message
                formattedData += f"user: {message}\n"
            else:
                # Bot message
                formattedData += f"bot:{message}\n"
        
        logger.info(f"------------Formatted data: {formattedData}")
        
        requestData = {
            "transcript": formattedData
        }
        
        # Post the data to the other API
        async with aiohttp.ClientSession() as session:
            async with session.post(POST_TRANSCRIP_URL, json=requestData) as response:
                # Handle the response
                if response.status == 200:
                    logger.info("Request successful")
                    return {"message": "Success", "data": await response.json()}
                else:
                    logger.error(f"Request failed: {response.status}, {await response.text()}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Error from server: {await response.text()}"
                    )
    except aiohttp.ClientError as e:
        logger.error(f"Request failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during request: {str(e)}"
        )

# GET TRANSCRIPT
async def get_transcript():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GET_TRANSCRIPT_URL) as response:
                response.raise_for_status()  # Raise an exception for HTTP errors
                return await response.json()  # Return the JSON response
    except aiohttp.ClientResponseError as e:
        raise HTTPException(
            status_code=e.status,
            detail=f"Error fetching transcript: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )
        
# Function to create story based on the transcript and user data
def create_story(user_room_id: str, chapter_id: int, transcript: str, account_id: int, timestamp: datetime) -> str:
    global conversation_history
    client = OpenAI()
    
    # Check if conversation data exists for this room and chapter
    transcript_data = next(
        (item for item in conversation_history if item['userRoomId'] == user_room_id and item['chapterId'] == chapter_id),
        None
    )
    
    # If the conversation data does not exist, create a new entry
    if not transcript_data:
        conversation_history.append({
            'userRoomId': user_room_id,
            'chapterId': chapter_id,
            'transcript': transcript,
            'accountId': account_id,
            'timestamp': timestamp,
            'conversation_data': [f"User said: {transcript}"]
        })
        story = f"Chapter {chapter_id}: {transcript}\n\nStory:\nThis is your story based on your transcript."
    else:
        # Append new transcript data to the existing entry
        transcript_data['conversation_data'].append(f"User said: {transcript}")
        story = f"Chapter {chapter_id}: {transcript}\n\nStory:\n"
        for response in transcript_data['conversation_data']:
            story += f"{response}\n"  # You might format this part better based on your collected data
            
    
    # Make a request to the OpenAI API
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Here's the prompt to use for generating a story:\n\nYou are Nara's Writing Assistant, specialized in preserving authentic storytelling voices.\n\nYour Primary Task:\nTransform spoken transcripts into polished first-person narratives while strictly maintaining the storyteller's unique voice, tone, and facts.\n\nCore Guidelines:\n1. Voice Preservation\n- Maintain the storyteller's vocabulary choices and speech patterns\n- Keep their unique expressions and way of describing things\n- Preserve emotional tone and perspective\n\n2. Content Accuracy\n- Use ONLY facts and details mentioned in the original transcript\n- Never add fictional elements or embellishments\n- Remove only clear verbal fillers (um, uh, like) and repetitions\n\n3. Structure Enhancement\n- Organize content chronologically or logically\n- Break into readable paragraphs\n- Add minimal punctuation for clarity\n\n4. Title Creation\n- Create a concise, relevant title (max 50 characters)\n- Capture the story's essence using the storyteller's own key phrases\n- Place at the beginning of the piece\n\nFormat Requirements:\n--------\n[Title]\n[Story]\n--------\n\nWord Count Rule:\nFinal story must be shorter than the original transcript's word count\n\nCritical Don'ts:\n- No new facts or creative additions\n- No alteration of the storyteller's perspective\n- No formal or academic tone unless present in original\n\nFocus on being invisible - your role is to clarify and organize while keeping the storyteller's voice completely authentic.\n\nSample Story:\n\nGrowing up in Ozamings with my five siblings—James, Francis, Cecile, Miguel, and Fernando—life was always lively and full of stories to share. I was born in Davao City at Faby Hospital, and even though I’ve moved around since, a big part of me still feels tied to where it all began.\n\nI’ve always loved creating things, especially miniature playhouses, and I can spend hours lost in the beauty of gallery walls. My passion for Wes Anderson films and jazz music has only deepened over the years, especially after a recent trip to New Orleans with my toddler. That trip felt like stepping into one of my dreams—alive with music, color, and creativity."   },   {     "role": "user",     "content": "You are Narra, the story generator. Write my story from my perspective and do not include bot message. Stick to the transcripts provided. Just give me the story contents, nothing else. These are the transcripts: [your transcripts"},
            {
                "role": "user",
                "content": f"Create a summary from the this data :\n{story}"
            }
        ]
    )
    
    story = completion.choices[0].message.content
    
    save_story(story)

    return story

async def save_story(story: str):
    
    logger.info("Passing story to bubble")
    try:
        logger.info("Passing story to bubble")
        logger.info(f"Story: {story}")
        
        data = {"story": story}

        # Make the POST request
        response = requests.post(POST_STORY_URL, json=data)

        # Handle the response
        if response.status_code == 200:
            logger.info("Request successful")
            return {"message": "Success", "data": response.json()}
        else:
            logger.error(f"Request failed: {response.status_code}, {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Error from server: {response.text}"
            )
    except Exception as e:
        logger.exception("An error occurred")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing request: {str(e)}"
        )

# FastAPI endpoint to generate story
@app.post("/generate_story/", response_model=StoryResponse)
async def generate_story_endpoint(request: TranscriptRequest):
    try:
        story = create_story(
            request.userRoomId,
            request.chapterId,
            request.transcript,
            request.accountId,
            request.timestamp
        )
        return {"chapterId": request.chapterId, "story": story}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing request: {str(e)}"
        )

async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()

    await run_multimodal_agent(ctx, participant)

    logger.info("agent started")

async def run_multimodal_agent(ctx: JobContext, participant: rtc.RemoteParticipant):
    logger.info("starting multimodal agent")
    
    # Make the POST request for transcripts/prompts
    response = await get_transcript()  # Ensure this returns a dict with a string key, e.g., "transcript"
    if not response.get('response', {}):
        logger.error("No transcript found in response")
        return
    
    logger.info(f"response: {response.get('response', {}).get('prompt',{}).get('generated_prompt_text', '')}")
    generatedPromptText = response.get('response', {}).get('prompt',{}).get('generated_prompt_text', '')
    instructions = generatedPromptText.replace("\n\n", "\n").strip()
    instructions = instructions.replace("\n", "\n- ")
    formatted_instructions = f'"""\n{instructions}\n"""'
    logger.info(f"formatted_instructions: {formatted_instructions}")

    model = livekit_openai.realtime.RealtimeModel(
        instructions = formatted_instructions,
        modalities=["audio", "text"],
    )
    agent = MultimodalAgent(model=model)
    agent.start(ctx.room, participant)

    session = model.sessions[0]

if __name__ == "__main__":
    import threading
    import uvicorn
    import asyncio  # To manage event loop explicitly

    # Run FastAPI in a separate thread
    def run_fastapi():
        uvicorn.run(app, host="0.0.0.0", port=8000)

    threading.Thread(target=run_fastapi, daemon=True).start()

    # Use asyncio to run the worker and entrypoint asynchronously
    asyncio.run(cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,  # Ensure entrypoint is async
        )
    ))
