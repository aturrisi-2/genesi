import uvicorn
from fastapi import FastAPI

from core.state import CognitiveState
from api.user import router as user_router
from api.chat import router as chat_router

app = FastAPI()
app.include_router(user_router)
app.include_router(chat_router)

@app.get("/state/{user_id}")
async def get_state(user_id: str):
    state = CognitiveState.build(user_id)
    def serialize_event(event):
        event_dict = event.to_dict()
        if hasattr(event, 'decayed_affect'):
            event_dict['decayed_affect'] = event.decayed_affect
        return event_dict
        
    return {
        "user": state.user.to_dict(),
        "recent_events": [serialize_event(e) for e in state.recent_events],
        "context": state.context
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)