
from shiny import App, render, ui, reactive
import os
import shutil
from openai import OpenAI
from langchain_core.documents import Document
from dotenv import load_dotenv
import fitz  # PyMuPDF
from datetime import datetime
import PyPDF2
# from docx import Document as DocxDocument
from datetime import datetime
import pytz
from styles import styles_app


load_dotenv()

# Ensures the uploaded_files directory exists
if not os.path.exists('uploaded_files'):
    os.makedirs('uploaded_files')

# Set OpenAI API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# used so that any files uploaded have the correct syntax
def sanitize_filename(filename):
    return "".join(c if c.isalnum() else "_" for c in filename)

def get_time_for_location(timezone):
    return datetime.now(pytz.timezone(timezone)).strftime("%H:%M")

def read_file_content(file_path):
    _, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()

    try:
        if file_extension in ['.txt', '.csv', '.py', '.json']:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif file_extension == '.pdf':
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                return "\n".join(page.extract_text() for page in pdf_reader.pages)
        elif file_extension == '.docx':
            doc = DocxDocument(file_path)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        else:
            return f"File type {file_extension} is not supported for content viewing."
    except Exception as e:
        return f"Error reading file: {str(e)}"

app_ui = ui.page_fluid(
    ui.tags.style(styles_app),
    ui.row(
        ui.column(4,
            ui.div({"class": "sidebar"},
                # ui.output_ui("logo_output"),
                ui.h2("File Upload", style="color: #0E4878;"),
                ui.input_file("file_upload", "Upload a file by clicking Browse below", multiple=True),
                ui.output_text_verbatim("file_info"),
                ui.markdown("### Uploaded files:"),
                ui.output_ui("uploaded_files_list"),
                ui.input_action_button("process_button", "Summarize Selected Files", class_="btn-primary mt-2"),
                ui.input_action_button("delete_button", "Delete Selected Files", class_="btn-danger mt-2"),
                ui.div(
                    ui.input_text_area("user_question", "Ask a question about the file(s):"),
                    class_="mt-3"
                ),
                ui.input_action_button("submit_question", "Submit Question", class_="btn-primary mt-2"),
            )
        ),
        ui.column(8,
            ui.div({"class": "main-content"},
                # ui.tags.img(src="whitelogo.jpg", class_="logo"),
                ui.div({"class": "time-display"},
                    ui.output_text("time_display"),
                ),
                ui.h1({"class": "greeting"}, "Welcome!  Bienvenue!  !أهلا وسهلا"),
                ui.h3("Conversation", class_="section-header"),
                ui.output_text_verbatim("process_output"),
            )
        )
    )
)

# parent server
def server(input, output, session):
    # defined so that no errors occur
    delete_trigger = reactive.Value(0)
    process_output_value = reactive.Value("")
    conversation_history = reactive.Value([])
    
    # @output
    # @render.ui
    # def logo_output():
    #     logo_path = "www/whitelogo.jpg"  # Adjust this path if necessary
    #     if os.path.exists(logo_path):
    #         return ui.tags.img(src="whitelogo.jpg", class_="logo")
    #     else:
    #         return ui.tags.div(
    #             ui.tags.p(f"Logo file not found at: {logo_path}", class_="logo-error"),
    #             ui.tags.p(f"Current working directory: {os.getcwd()}", class_="logo-error"),
    #             ui.tags.p(f"Files in www folder: {os.listdir('www')}", class_="logo-error")
    #         )
    
    @output
    @render.text
    def time_display():
        dc_time = get_time_for_location("US/Eastern")
        morocco_time = get_time_for_location("Africa/Casablanca")
        return f"⏲D.C.: {dc_time} 🕰Morocco: {morocco_time}"
    
    @output
    @render.text
    def file_info():
        if input.file_upload() is None:
            return "No file uploaded this session."
        
        files = input.file_upload()
        file_details = []
        
        # a for loop that moves the files to the uploaded_files directory - could be used to move file_info from where its currently displayed in the ui.
        for file in files:
            filename = file["name"]
            file_path = file["datapath"]
            save_path = os.path.join("uploaded_files", filename)
            shutil.move(file_path, save_path)
            file_details.append(f"File uploaded: {filename}")
        
        return "\n".join(file_details)
    
    @output
    @render.ui
    def uploaded_files_list():
        delete_trigger()
        # checks if there are any files in the directory
        file_list = os.listdir('uploaded_files')
        if not file_list:
            return ui.p("No files available.")
        
        checkboxes = [ui.div(
            ui.input_checkbox(f"select_{sanitize_filename(file)}", file, value=True),
            class_="mb-2"
        ) for file in file_list]
        return ui.div(*checkboxes)
    
    @reactive.Effect
    @reactive.event(input.delete_button)
    def delete_selected_files():
        file_list = os.listdir('uploaded_files')
        for file in file_list:
            checkbox_id = f"select_{sanitize_filename(file)}"
            if input[checkbox_id]():
                try:
                    os.remove(os.path.join('uploaded_files', file))
                except Exception as e:
                    print(f"Error deleting {file}: {e}")
        
        delete_trigger.set(delete_trigger() + 1)

    @output
    @render.text
    def process_output():
        return process_output_value()

    @reactive.Effect
    @reactive.event(input.process_button)
    def process_selected_files():
        file_list = os.listdir('uploaded_files')
        selected_files = []
        for file in file_list:
            checkbox_id = f"select_{sanitize_filename(file)}"
            if input[checkbox_id]():
                selected_files.append(os.path.join('uploaded_files', file))
        
        if not selected_files:
            process_output_value.set("No files selected for processing.")
            return
        
        output_list = []
        for file_path in selected_files:
            content = read_file_content(file_path)
           
            document = Document(page_content=content)
            # Process the document using LangChain and OpenAI API
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes documents."},
                    {"role": "user", "content": f"Summarize the following document: {content}"}
                ],
                max_tokens=150
            )
            summary = response.choices[0].message.content
            output_list.append(f"File: {os.path.basename(file_path)}\nSummary: {summary.strip()}")

        process_output_value.set("\n\n".join(output_list))

    @reactive.Effect
    @reactive.event(input.submit_question)
    def handle_question():
        question = input.user_question()
        if not question:
            process_output_value.set("Please enter a question.")
            return

        file_list = os.listdir('uploaded_files')
        selected_files = []
        for file in file_list:
            checkbox_id = f"select_{sanitize_filename(file)}"
            if input[checkbox_id]():
                selected_files.append(os.path.join('uploaded_files', file))

        if not selected_files:
            process_output_value.set("No files selected. Please select at least one file.")
            return

        document_contents = []
        for file_path in selected_files:
            content = read_file_content(file_path)
            document_contents.append(f"File: {os.path.basename(file_path)}\nContent: {content}")
        
        combined_content = "\n\n".join(document_contents)

        # CHANGED: Reset the conversation history for a new question to avoid issues.
        history = []  # This resets the conversation history for each new question.

        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided documents."},
            {"role": "user", "content": f"Here are the documents:\n\n{combined_content}\n\nPlease answer the following question based on these documents: {question}"}
        ] 
        # REMOVED: The line that extended messages with history has been removed since history is reset.

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=300
            )
            answer = response.choices[0].message.content

            # CHANGED: Optionally append the question and answer to the history for future use.
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
            conversation_history.set(history)  # History is now only updated if you want to keep it for future use.

            output = f"Question: {question}\n\nAnswer: {answer}"
            process_output_value.set(output)
        except Exception as e:
            process_output_value.set(f"An error occurred: {str(e)}")

app = App(app_ui, server)

if __name__ == "__main__":
    app.run()

