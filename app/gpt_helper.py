# It is here for the part that connects to the GPT API
# This file summarizes the course material

from openai import OpenAI
import os

_client = None
# Grabs the clients name
def _get_client():
    global _client
    if _client is None:
        # Uses os.getenv to check the project directories to searches if such client exists
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

# Prompts an instruction sheet for the API to further send to GPT
Sys_Message = (
    "You are a helpful assistant for a University of Saskatchewan CS student. "
    "Given a course code and possibly a description, produce a short, "
    "plain-English summary (about 3–5 sentences) that covers focus, workload, and prerequisites."
)


# The string variable is defined to grab the CS class name
# The 'course_code' is a string which interacts with the client to input the course name
# The 'desc' parameter is defined if the client wants to add a course description
#It is currently set to None if not required by the client
def summarize_course(course_code: str, desc: str | None = None) -> str:
    # Ensures the course code or name is consistently the same format overall each input
    course_code = (course_code or "").strip().upper()
    if not course_code:
        return "Please provide a course code (e.g., CMPT 270)."
    # Holds users entered data
    user = f"Course: {course_code}\n"
    # If a description is entered updates the 'user' variable
    if desc:
        user += f"Description: {desc}\n"
    try:
        client = _get_client()
        # Calls the OPENAI API through the client object
        # Tell the API what detail to further send forward to OPENAI
        resp = client.chat.completions.create(
            # Sets the gpt model to 4o-mini
            model="gpt-4o-mini",
            # Lets gpt know the user and system details
            messages=[
                {"role": "system", "content": Sys_Message},
                {"role": "user", "content": user}
            ],
            # Sets the temperature to 0.4 which controls the creativity to more random
            temperature=0.4,
            #Sets teh max length of the gpt reply to 240
            max_tokens=240,
        )
        # Takes the first gpt response and strips any white spaces or extra lines
        return resp.choices[0].message.content.strip()
    # For the odd reason if gpt crashes
    except Exception as e:
        return "Sorry could not generate a summary right now. Please Try again in a minute."


