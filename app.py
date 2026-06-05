from flask import Flask, render_template, request
from llm_engine import build_full_prompt, ask_openai, parse_multiple_outputs
import logging

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    article_input = ""
    output = []
    message = ""

    if request.method == "POST":
        article_input = request.form.get("article", "")
        if not article_input.strip():
            message = "Please enter an article."
        else:
            try:
                full_prompt = build_full_prompt(article_input)
                response = ask_openai(full_prompt)

                # Log raw GPT output for debugging
                logger.info("GPT RAW RESPONSE:\n%s", response)

                output = parse_multiple_outputs(response)
            except Exception as e:
                message = f"Error: {str(e)}"

    return render_template("index.html",
                           article_input=article_input,
                           output=output,
                           message=message)

if __name__ == "__main__":
    app.run(debug=True)