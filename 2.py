import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
import json
import requests
import threading
import queue
import pyperclip

# --- AnkiConnect Configuration ---
ANKI_CONNECT_URL = "http://localhost:8765"

# --- Main Application Class ---
class AnkiToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Anki Workflow Suite v3.0")
        self.root.geometry("850x750")
        
        style = ttk.Style(self.root)
        style.theme_use('clam')

        self.notebook = ttk.Notebook(root, padding=10)
        self.notebook.pack(expand=True, fill='both')

        # Create and add the three tabs in a logical workflow order
        self.prompt_tab = PromptGeneratorTab(self.notebook)
        self.importer_tab = AnkiImporterTab(self.notebook)
        self.converter_tab = NewlineConverterTab(self.notebook)

        self.notebook.add(self.prompt_tab, text='1. Prompt Generator')
        self.notebook.add(self.importer_tab, text='2. Anki Importer')
        self.notebook.add(self.converter_tab, text='Text Helper')


# --- Prompt Generator Tab ---
class PromptGeneratorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.placeholder_entries = {}

        paned_window = ttk.PanedWindow(self, orient='horizontal')
        paned_window.pack(fill='both', expand=True, padx=5, pady=5)

        template_frame = ttk.LabelFrame(paned_window, text="1. Paste Prompt Template", padding=10)
        paned_window.add(template_frame, weight=1)
        self.template_text = scrolledtext.ScrolledText(template_frame, wrap=tk.WORD, height=10, relief=tk.FLAT)
        self.template_text.pack(fill='both', expand=True, pady=(0, 5))
        self.template_text.bind("<KeyRelease>", self.analyze_placeholders)

        right_pane_frame = ttk.Frame(paned_window)
        paned_window.add(right_pane_frame, weight=1)

        placeholder_frame = ttk.LabelFrame(right_pane_frame, text="2. Fill Placeholders", padding=10)
        placeholder_frame.pack(fill='x', expand=False, pady=(0, 10))
        self.placeholder_fields_frame = ttk.Frame(placeholder_frame)
        self.placeholder_fields_frame.pack(fill='x', expand=True)

        output_frame = ttk.LabelFrame(right_pane_frame, text="3. Completed Prompt", padding=10)
        output_frame.pack(fill='both', expand=True)
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=10, state='disabled', relief=tk.FLAT)
        self.output_text.pack(fill='both', expand=True, pady=(0, 5))
        
        button_frame = ttk.Frame(output_frame)
        button_frame.pack(fill='x')
        ttk.Button(button_frame, text="Copy to Clipboard", command=self.copy_prompt).pack(side='left', expand=True, fill='x', padx=(0, 5))
        ttk.Button(button_frame, text="Save to File...", command=self.save_prompt).pack(side='left', expand=True, fill='x')

    def analyze_placeholders(self, event=None):
        template_content = self.template_text.get("1.0", tk.END)
        placeholders = sorted(list(set(re.findall(r'\{([^{}]+)\}', template_content))))
        
        for widget in self.placeholder_fields_frame.winfo_children(): widget.destroy()
        self.placeholder_entries.clear()

        for i, name in enumerate(placeholders):
            ttk.Label(self.placeholder_fields_frame, text=f"{name}:").grid(row=i, column=0, sticky='w', padx=5, pady=2)
            entry = ttk.Entry(self.placeholder_fields_frame)
            entry.grid(row=i, column=1, sticky='ew', padx=5, pady=2)
            entry.bind("<KeyRelease>", self.generate_prompt)
            self.placeholder_entries[name] = entry
        
        self.placeholder_fields_frame.columnconfigure(1, weight=1)
        self.generate_prompt()

    def generate_prompt(self, event=None):
        completed_prompt = self.template_text.get("1.0", tk.END)
        for name, entry_widget in self.placeholder_entries.items():
            completed_prompt = completed_prompt.replace(f'{{{name}}}', entry_widget.get())
        
        self.output_text.config(state='normal')
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", completed_prompt)
        self.output_text.config(state='disabled')

    def copy_prompt(self):
        prompt_content = self.output_text.get("1.0", tk.END).strip()
        if prompt_content:
            pyperclip.copy(prompt_content)
            messagebox.showinfo("Success", "Prompt copied to clipboard!")
        else: messagebox.showwarning("Warning", "Nothing to copy.")

    def save_prompt(self):
        prompt_content = self.output_text.get("1.0", tk.END).strip()
        if not prompt_content: messagebox.showwarning("Warning", "Nothing to save."); return
        filename = filedialog.asksaveasfilename(title="Save Prompt As", filetypes=(("Text Files", "*.txt"), ("All files", "*.*")), defaultextension=".txt")
        if filename:
            with open(filename, 'w', encoding='utf-8') as f: f.write(prompt_content)
            messagebox.showinfo("Success", f"Prompt saved to {filename}")


# --- Anki Importer Tab ---
class AnkiImporterTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.file_path = tk.StringVar()
        self.status_queue = queue.Queue()
        self.current_note_fields = []

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        file_frame = ttk.LabelFrame(main_frame, text="1. Select Generated Card File", padding="10")
        file_frame.pack(fill="x", pady=5)
        ttk.Entry(file_frame, textvariable=self.file_path, state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(file_frame, text="Browse...", command=self.select_file).pack(side="left")

        anki_frame = ttk.LabelFrame(main_frame, text="2. Configure Anki Target", padding="10")
        anki_frame.pack(fill="x", pady=10)
        anki_frame.columnconfigure(1, weight=1)
        
        ttk.Label(anki_frame, text="Target Deck:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.deck_combobox = ttk.Combobox(anki_frame, state="readonly")
        self.deck_combobox.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(anki_frame, text="Note Type:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.model_combobox = ttk.Combobox(anki_frame, state="readonly")
        self.model_combobox.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.model_combobox.bind("<<ComboboxSelected>>", self.on_model_select)

        ttk.Button(anki_frame, text="Refresh Lists", command=self.populate_dropdowns).grid(row=0, column=2, rowspan=2, padx=10)

        fields_frame = ttk.Frame(anki_frame)
        fields_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(5,0))
        ttk.Label(fields_frame, text="Expected Fields:").pack(side='left', anchor='n')
        self.fields_label = ttk.Label(fields_frame, text="Select a Note Type to see its fields.", wraplength=550, foreground="gray")
        self.fields_label.pack(side='left', fill='x', expand=True, padx=5)

        action_frame = ttk.LabelFrame(main_frame, text="3. Execute Import", padding="10")
        action_frame.pack(fill="both", expand=True, pady=5)
        self.import_button = ttk.Button(action_frame, text="Start Import", command=self.start_import_thread)
        self.import_button.pack(pady=10)
        self.status_box = scrolledtext.ScrolledText(action_frame, height=10, wrap=tk.WORD, state="disabled", relief=tk.FLAT)
        self.status_box.pack(fill="both", expand=True, pady=5)
        
        self.populate_dropdowns()
        self.after(100, self.process_status_queue)

    def log_status(self, message): self.status_queue.put(message)

    def process_status_queue(self):
        while not self.status_queue.empty():
            message = self.status_queue.get_nowait()
            self.status_box.config(state="normal")
            self.status_box.insert(tk.END, message + "\n")
            self.status_box.see(tk.END)
            self.status_box.config(state="disabled")
        self.after(100, self.process_status_queue)

    def invoke_anki_connect(self, action, **params):
        try:
            payload = json.dumps({"action": action, "version": 6, "params": params})
            response = requests.post(ANKI_CONNECT_URL, data=payload, timeout=5)
            response.raise_for_status()
            result = response.json()
            if result.get('error'):
                error_msg = result['error']
                if action == 'addNotes' and isinstance(error_msg, list):
                    self.log_status(f"AnkiConnect batch error details: {error_msg}")
                elif action == 'addNote':
                    raise Exception(f"AnkiConnect Error: {error_msg}")
                else:
                    self.log_status(f"AnkiConnect Error: {error_msg}")
                return None
            return result.get('result')
        except requests.exceptions.RequestException as e:
            self.log_status(f"ERROR: Could not connect to AnkiConnect. Is Anki open? ({str(e)})")
            return None
        except Exception as e:
            if action == 'addNote':
                raise e
            else:
                self.log_status(f"ERROR: {str(e)}")
                return None

    def populate_dropdowns(self):
        self.log_status("Attempting to connect to Anki...")
        deck_names = self.invoke_anki_connect('deckNames')
        model_names = self.invoke_anki_connect('modelNames')
        if deck_names is not None and model_names is not None:
            self.deck_combobox['values'] = sorted(deck_names)
            self.model_combobox['values'] = sorted(model_names)
            self.log_status("Successfully fetched decks and note types.")
            if deck_names: self.deck_combobox.set('Default' if 'Default' in deck_names else deck_names[0])
            if model_names: self.model_combobox.set(model_names[0])
            self.on_model_select()
        else:
            self.log_status("Failed to get data. Check Anki connection and click 'Refresh Lists'.")

    def on_model_select(self, event=None):
        model_name = self.model_combobox.get()
        if not model_name: return
        fields = self.invoke_anki_connect('modelFieldNames', modelName=model_name)
        if fields:
            self.current_note_fields = fields
            self.fields_label.config(text=", ".join(fields), foreground="black")
        else:
            self.current_note_fields = []
            self.fields_label.config(text=f"Could not fetch fields for '{model_name}'.", foreground="red")

    def select_file(self):
        filename = filedialog.askopenfilename(title="Select Card Data File", filetypes=(("Text Files", "*.txt"), ("All files", "*.*")))
        if filename: self.file_path.set(filename); self.log_status(f"Selected file: {filename}")

    def start_import_thread(self):
        self.import_button.config(state="disabled")
        threading.Thread(target=self.import_worker, daemon=True).start()

    def import_worker(self):
        file, deck, model = self.file_path.get(), self.deck_combobox.get(), self.model_combobox.get()

        if not all([file, deck, model, self.current_note_fields]):
            self.log_status("ERROR: Please select a file, a valid deck, and a note type with detectable fields.")
            self.import_button.config(state="normal"); return

        self.log_status("\n--- Starting Import Process ---")
        try:
            with open(file, 'r', encoding='utf-8') as f: content = f.read()
            # 确保您的Prompt模板使用 ---END-CARD--- 作为分隔符
            card_blocks = [block for block in content.strip().split('---END-CARD---') if block.strip()]
            pattern_parts = [re.escape(field) + r':::(.*?)' for field in self.current_note_fields]
            pattern_str = "".join(pattern_parts[:-1]) + re.escape(self.current_note_fields[-1]) + r':::(.*)'
            card_pattern = re.compile(pattern_str, re.DOTALL)
            parsed_cards = []
            for i, block in enumerate(card_blocks):
                match = card_pattern.search(block)
                if match:
                    field_values = [val.strip() for val in match.groups()]
                    if len(field_values) != len(self.current_note_fields):
                        self.log_status(f"WARNING: Card #{i+1} field count mismatch. Expected {len(self.current_note_fields)}, got {len(field_values)}")
                        continue
                    if not field_values[0].strip():
                        self.log_status(f"WARNING: Card #{i+1} has empty first field (usually required)")
                        continue
                    card_data = dict(zip(self.current_note_fields, field_values))
                    parsed_cards.append(card_data)
                else: self.log_status(f"WARNING: Card #{i+1} could not be parsed. Check field names and order.")

            self.log_status(f"Parsing complete. Found {len(parsed_cards)} valid cards.")
            if not parsed_cards: self.import_button.config(state="normal"); return
        except Exception as e:
            self.log_status(f"ERROR: Failed during file parsing. {e}")
            self.import_button.config(state="normal"); return

        batch_size = 25
        total_successful = 0
        total_failed = 0
        
        for i in range(0, len(parsed_cards), batch_size):
            batch = parsed_cards[i:i + batch_size]
            notes_to_add = []
            
            for j, card in enumerate(batch):
                # ★★★★★【代码修正处】★★★★★
                # 我们不再手动进行HTML转义，因为这会破坏需要HTML的字段
                cleaned_fields = {field_name: field_value.strip() for field_name, field_value in card.items()}
                
                note = {
                    "deckName": deck,
                    "modelName": model,
                    "fields": cleaned_fields,
                    "tags": [],
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck"
                    }
                }
                notes_to_add.append(note)
            
            self.log_status(f"Processing batch {i//batch_size + 1}/{(len(parsed_cards) + batch_size - 1)//batch_size} ({len(batch)} notes)...")
            
            try:
                # First, try to add the entire batch at once.
                result = self.invoke_anki_connect('addNotes', notes=notes_to_add)

                # The `addNotes` command is transactional. If one card fails, it returns a list of `None`.
                # If the result is not None and the first element is not None, the whole batch was successful.
                if result and result[0] is not None:
                    total_successful += len(batch)
                    self.log_status(f"  All {len(batch)} notes in batch added successfully.")
                else:
                    # The batch failed. Fall back to adding notes one by one.
                    self.log_status("  Batch import failed. Retrying notes individually...")
                    batch_successful = 0
                    batch_failed = 0
                    
                    for k, note_to_add in enumerate(notes_to_add):
                        try:
                            # Try adding a single note.
                            single_result = self.invoke_anki_connect('addNote', note=note_to_add)
                            if single_result:
                                batch_successful += 1
                            else:
                                # This path is unlikely if invoke_anki_connect raises an exception on error, but is here for safety.
                                batch_failed += 1
                                first_field_name = self.current_note_fields[0]
                                first_field_value = note_to_add['fields'].get(first_field_name, "N/A").strip()
                                self.log_status(f"  --> SKIPPED (failed import): Card starting with '{first_field_value}'")

                        except Exception as single_error:
                            # This is the expected path for a single note failure.
                            batch_failed += 1
                            first_field_name = self.current_note_fields[0]
                            first_field_value = note_to_add['fields'].get(first_field_name, "N/A").strip()
                            # Clean up the error message from AnkiConnect if possible
                            error_message = str(single_error)
                            if "duplicate" in error_message.lower():
                                error_message = "Duplicate card."
                            self.log_status(f"  --> SKIPPED (failed import): Card starting with '{first_field_value}'. Reason: {error_message}")
                    
                    total_successful += batch_successful
                    total_failed += batch_failed
                    self.log_status(f"  Individual retry result: {batch_successful} successful, {batch_failed} failed.")

            except Exception as batch_error:
                self.log_status(f"  A critical error occurred during batch processing: {str(batch_error)}")
                total_failed += len(batch)

        self.log_status(f"\n--- Import Complete ---")
        self.log_status(f"Total processed: {len(parsed_cards)} cards")
        self.log_status(f"Successfully imported: {total_successful} notes")
        if total_failed > 0: 
            self.log_status(f"Failed imports: {total_failed} notes")
            self.log_status("Common causes of failures: duplicate cards, empty required fields, or formatting issues")
        
        self.import_button.config(state="normal")

# --- NEW: Text Helper Tab ---
class NewlineConverterTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill='both', expand=True)
        
        main_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        ttk.Label(main_frame, text="Enter words/phrases (one per line):").grid(row=0, column=0, sticky='w', pady=(0,5))
        self.input_text = scrolledtext.ScrolledText(main_frame, height=10, relief=tk.FLAT)
        self.input_text.grid(row=1, column=0, sticky='nsew', pady=5)

        ttk.Button(main_frame, text="Convert to \\n format", command=self.convert_text).grid(row=2, column=0, pady=10)

        ttk.Label(main_frame, text="Output:").grid(row=3, column=0, sticky='w', pady=5)
        self.output_text = scrolledtext.ScrolledText(main_frame, height=10, state='disabled', relief=tk.FLAT)
        self.output_text.grid(row=4, column=0, sticky='nsew', pady=5)

        ttk.Button(main_frame, text="Copy Output", command=self.copy_output).grid(row=5, column=0, pady=10)

    def convert_text(self):
        lines = self.input_text.get("1.0", tk.END).strip().splitlines()
        result = "\\n".join(lines)
        self.output_text.config(state='normal')
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, result)
        self.output_text.config(state='disabled')

    def copy_output(self):
        output_content = self.output_text.get("1.0", tk.END).strip()
        if output_content:
            pyperclip.copy(output_content)
            messagebox.showinfo("Success", "Output copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "Nothing to copy.")


if __name__ == "__main__":
    app_root = tk.Tk()
    app = AnkiToolApp(app_root)
    app_root.mainloop()