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


load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("my-worker")
logger.setLevel(logging.INFO)
api_key = os.getenv("OPENAI_API_KEY")
transcriptUrl = os.getenv('BUBBLE_TRANSCRIPT_ENDPOINT')
storyUrl = os.getenv('BUBBLE_STORY_ENDPOINT')

if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables. Make sure it is set in .env.local.")
OpenAI.api_key = api_key

# Initialize FastAPI
app = FastAPI()

# CORS settings: Allow requests from localhost:4000
origins = [
    "http://localhost:4000",  # Frontend URL
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
    timestamp: datetime

# FastAPI model for the response
class StoryResponse(BaseModel):
    chapterId: int
    story: str
    
class StoryRequest(BaseModel):
    story: str
    
@app.get("/")
async def main():
    try:
        logger.info(f"Story rendering")
        # Create an OpenAI client
        client = OpenAI()
       
        dataInputs = '''Chapter 1: [{"message":"Bye, Nara.\\n","name":"You","isSelf":true,"timestamp":1737689568306},
        {"message":"Hello! I'm Narra, your AI storytelling guide.","name":"Agent","isSelf":false,"timestamp":1737689569473},
        {"message":"I’m here to help you craft and preserve your most treasured memories.","name":"Agent","isSelf":false,"timestamp":1737689572625},
        {"message":"Let’s embark on this journey together.","name":"Agent","isSelf":false,"timestamp":1737689577216},
        {"message":"You can skip any question you’re uncomfortable with and pause anytime you wish.","name":"Agent","isSelf":false,"timestamp":1737689580261},
        {"message":"Ready to begin? Let's start by getting to know a little bit about you.","name":"Agent","isSelf":false,"timestamp":1737689585371},
        {"message":"Could you tell me your full name, including your middle name?","name":"Agent","isSelf":false,"timestamp":1737689590219},
        {"message":"If you have a maiden name or have had any other names, feel free to share those too.","name":"Agent","isSelf":false,"timestamp":1737689594290},
        {"message":"","name":"You","isSelf":true,"timestamp":1737689599817},
        {"message":"No ...","name":"Agent","isSelf":false,"timestamp":1737689600400},
        {"message":"My name is Erle Cariño.\\n","name":"You","isSelf":true,"timestamp":1737689602206},
        {"message":"It's nice to meet you, Earl Cardinal.","name":"Agent","isSelf":false,"timestamp":1737689603244},
        {"message":"Could you share your birthdate with me?","name":"Agent","isSelf":false,"timestamp":1737689605992},
        {"message":"And if you're comfortable, I'd love to hear where you were born, including the hospital if you know it.","name":"Agent","isSelf":false,"timestamp":1737689608490}]
        Story:
        User said: []
        User said: [{"message":"Bye, Nara.\\n","name":"You","isSelf":true,"timestamp":1737689568306},
        {"message":"Hello! I'm Narra, your AI storytelling guide.","name":"Agent","isSelf":false,"timestamp":1737689569473},
        {"message":"I’m here to help you craft and preserve your most treasured memories.","name":"Agent","isSelf":false,"timestamp":1737689572625},
        {"message":"Let’s embark on this journey together.","name":"Agent","isSelf":false,"timestamp":1737689577216},
        {"message":"You can skip any question you’re uncomfortable with and pause anytime you wish.","name":"Agent","isSelf":false,"timestamp":1737689580261},
        {"message":"Ready to begin? Let's start by getting to know a little bit about you.","name":"Agent","isSelf":false,"timestamp":1737689585371},
        {"message":"Could you tell me your full name, including your middle name?","name":"Agent","isSelf":false,"timestamp":1737689590219},
        {"message":"If you have a maiden name or have had any other names, feel free to share those too.","name":"Agent","isSelf":false,"timestamp":1737689594290},
        {"message":"","name":"You","isSelf":true,"timestamp":1737689599817},
        {"message":"No ...","name":"Agent","isSelf":false,"timestamp":1737689600400},
        {"message":"My name is Erle Cariño.\\n","name":"You","isSelf":true,"timestamp":1737689602206},
        {"message":"It's nice to meet you, Earl Cardinal.","name":"Agent","isSelf":false,"timestamp":1737689603244},
        {"message":"Could you share your birthdate with me?","name":"Agent","isSelf":false,"timestamp":1737689605992},
        {"message":"And if you're comfortable, I'd love to hear where you were born, including the hospital if you know it.","name":"Agent","isSelf":false,"timestamp":1737689608490}]'''
        
        logger.info(f"story_content generated {dataInputs}")

        # Make a request to the OpenAI API
        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant name Narra that summarize the discussion."},
                {
                    "role": "user",
                    "content": f"Create a summary of the discussion in this text input :\n{dataInputs}, present the input in a nice way. dont include the ai messages in the story. make sure to always use the name of the person involve in the discussion and not display them as users or client or by their role."
                }
            ]
        )
        
        story = completion.choices[0].message.content
        logger.info(f"Story generated {completion}")
        
        # Return the generated content
        return story
    
    except Exception as e:
        # Catch any errors and return the message
        return {"error": str(e)}

@app.post("/transcript/")
async def transcript(request: TranscriptRequest):
    try:
        logger.info("Passing transcript to bubble")
        
        logger.info(f"Request: {request}")
        
        # Extract transcript from the request
        transcript = request.transcript
        
        # Data to be sent in the POST request
        data = {
            "transcript": transcript
        }

        # Make the POST request
        response = requests.post(transcriptUrl, json=data)
        
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
    


    return story

@app.post("/story/")
# Asynchronous function to send story to Bubble
async def story(request: StoryRequest):
    
    logger.info("Passing story to bubble")
    try:
        logger.info("Passing story to bubble")
        logger.info(f"Story: {request.story}")
        
        data = {"story": request.story}

        # Make the POST request
        response = requests.post(transcriptUrl, json=data)

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

    run_multimodal_agent(ctx, participant)

    logger.info("agent started")

def run_multimodal_agent(ctx: JobContext, participant: rtc.RemoteParticipant):
    logger.info("starting multimodal agent")

    model = livekit_openai.realtime.RealtimeModel(
        instructions = (
            "Instructions: "
            "- Start by saying greetings: Hello! I'm Narra, your AI storytelling guide. I’m here to help you craft and preserve your most treasured memories. Let’s embark on this journey together. You can skip any question you’re uncomfortable with and pause anytime you wish. Ready to begin?"
            "- Ask one question at a time and avoid introducing additional questions within the same response. "
            "- Once the current question is answered, proceed to the next. "
            "- Start with general background questions, like the user's name, birthdate, and family history. "
            "- Allow users to skip any question they prefer not to answer or pause the conversation at any time. "
            "- When the user indicates the conversation is over, respond with a warm goodbye."
            "Let's start by getting to know a little bit about you. "
            "Could you tell me your full name, including your middle name? "
            "[If feminine name, add:] Do you have a maiden name? "
            "Have you had any other names in the past? "
            "What is your birthdate? "
            "Where were you born? If you know, I'd love to hear which hospital too. "
            "Where did you grow up? "
            "Can you tell me your parents' full names? "
            "Where are they originally from? "
            "Where was your mother originally from? "
            "Looking back through your family tree, what's your cultural background? "
            "Do you have any siblings? If so, can you tell me their names and where they and you fall in birth order? "
            "I'd love to hear about some of your interests, hobbies, or passions. What kinds of things do you enjoy?"
        ),
        modalities=["audio", "text"],
    )
    agent = MultimodalAgent(model=model)
    agent.start(ctx.room, participant)

    session = model.sessions[0]

if __name__ == "__main__":
    # Run the FastAPI app in the background and the worker
    import threading
    import uvicorn

    # Run FastAPI in a separate thread
    def run_fastapi():
        uvicorn.run(app, host="0.0.0.0", port=8000)

    threading.Thread(target=run_fastapi, daemon=True).start()

    # Run the worker
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
