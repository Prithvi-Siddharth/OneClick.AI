# Implementation Plan - Chatbot Usage Limit (5 chats/day)

To enforce a usage limit, we will transition the chatbot logic from a direct external call to a backend proxy. This allows us to track message counts in the database and block requests for users who have exceeded their daily allowance.

## Proposed Changes

### Database - Usage Tracking

#### [MODIFY] [models.py](file:///c:/Users/kanak/OneClick.AI/backend/app/models.py)
- **New Model**: `ChatUsage`
    - `id`: Primary Key
    - `user_id`: Integer (link to user)
    - `chat_date`: Date (UTC date of the chat)
    - `usage_count`: Integer (tracks number of messages sent)

### Backend - Chat Proxy API

#### [NEW] [chatbot.py](file:///c:/Users/kanak/OneClick.AI/backend/app/routers/chatbot.py)
- **Endpoint**: `POST /api/chat`
    - Require user authentication via `get_current_user_id`.
    - Check the current date (UTC).
    - Query `ChatUsage` for the user and today's date.
    - If `usage_count >= 5`:
        - Return `429 Too Many Requests` with a "Daily chat limit reached (5/5)" message.
    - If `usage_count < 5`:
        - Increment/Create `usage_count`.
        - Proxy the JSON `query` to the external AWS API: `https://yexxsx2pz2.execute-api.us-east-1.amazonaws.com/prod/ask`.
        - Return the bot's response to the frontend.

#### [MODIFY] [main.py](file:///c:/Users/kanak/OneClick.AI/backend/app/main.py)
- Include the new `chatbot.router`.

### Frontend - Chatbot UI

#### [MODIFY] [base.html](file:///c:/Users/kanak/OneClick.AI/backend/app/templates/base.html)
- **API Update**: Change `CHAT_API_URL` from the AWS endpoint to the local `/api/chat` endpoint.
- **Error Handling**: 
    - Improve the `sendChatMessage` function to check for `response.status === 429`.
    - Display the "Daily limit reached" message in the chat bubble if the backend blocks the request.

## Verification Plan

### Automated Tests
- Use the browser tool to:
    1. Log in as a user.
    2. Send 1-4 chat messages and verify they receive a response from the AI.
    3. Send the 6th chat message and verify that the chat shows an error bubble: "Daily chat limit reached".
    4. Verify that the limit is per-user (log in as another user and verify they can still chat).

### Manual Verification
- Verify that the chat history is preserved within the session (as it currently is) while the limit is enforced correctly by the backend.
