import gradio as gr
from pathlib import Path
import pandas as pd
from database import init_db
import api

# Ensure database exists
init_db()

def app_interface():
    # --- Event Handlers ---
    def on_scan(path_str):
        if not path_str:
            gr.Warning("Please enter a directory path.")
            return "No path provided.", gr.DataFrame(value=[])
        
        try:
            gr.Info(f"Starting scan of {path_str}...")
            # 1. Run Scan
            results = api.scan_directory(path_str)
            
            # 2. Save Run
            run = api.start_scan_run("janatpmp.db", path_str)
            scan_id = run.get('scan_run_id')
            
            # 3. Save Files & Projects
            for proj in results['projects']:
                 api.save_project("janatpmp.db", proj)
                 
            for file_dat in results['files']:
                file_dat['project_id'] = None # Link logic later
                api.save_file("janatpmp.db", scan_id, file_dat)
                
            # 4. Complete Run
            api.complete_scan_run("janatpmp.db", scan_id, results['stats']['total_files'], len(results['errors']))
            
            status_msg = f"Scan Complete. Found {results['stats']['total_files']} files."
            
            # Refresh data
            start_df = get_file_dataframe()
            return status_msg, start_df
            
        except Exception as e:
            raise gr.Error(f"Scan failed: {e}")

    def get_file_dataframe(search_query=None):
        if search_query:
            files = api.search_files("janatpmp.db", search_query)
        else:
            files = api.get_files("janatpmp.db", limit=500)
            
        if not files or (len(files) == 1 and 'error' in files[0]):
            return pd.DataFrame(columns=["Filename", "Extension", "Size", "Path"])
            
        # Transform for display
        data = []
        for f in files:
            data.append({
                "Filename": f['filename'],
                "Extension": f['extension'],
                "Size": f['size_bytes'],
                "Path": f['path']
            })
        return pd.DataFrame(data)

    def load_recents():
        return get_file_dataframe()

    # --- UI Components ---
    with gr.Blocks(title="JANATPMP") as demo:
        # Header
        with gr.Row():
            gr.Markdown("# JANATPMP v0.1 Alpha")

        with gr.Row():
            # LEFT PANEL (Stats)
            with gr.Column(scale=1):
                with gr.Accordion("Stats & Observability", open=True):
                    stat_total_files = gr.Number(label="Total Files", value=0, interactive=False)
                    stat_projects = gr.Number(label="Projects", value=0, interactive=False)
                    stat_last_scan = gr.Textbox(label="Last Scan", value="Never", interactive=False)
                    gr.Markdown("_(Real-time stats coming soon)_")

            # MIDDLE PANEL (Main Content)
            with gr.Column(scale=3):
                with gr.Tabs():
                    with gr.Tab("Inventory"):
                        gr.Markdown("### Codebase Inventory")
                        
                        with gr.Group():
                            with gr.Row():
                                scan_input = gr.Textbox(
                                    label="Directory Path", 
                                    placeholder="/mnt/c/Janat/...", 
                                    scale=4
                                )
                                scan_btn = gr.Button("Scan", variant="primary", scale=1)
                            
                            scan_status = gr.Textbox(label="Status", value="Ready", interactive=False)
                        
                        gr.Markdown("---")
                        
                        with gr.Row():
                            search_input = gr.Textbox(label="Search Files", placeholder="filename or extension...", scale=4)
                            search_btn = gr.Button("Search", scale=1)
                        
                        file_table = gr.DataFrame(
                            headers=["Filename", "Extension", "Size", "Path"],
                            interactive=False,
                            label="Indexed Files"
                        )

                    with gr.Tab("Projects"):
                        gr.Markdown("### Detected Projects (Stub)")
                        gr.Markdown("_Project list will appear here_")

                    with gr.Tab("Scans"):
                         gr.Markdown("### Scan History (Stub)")
                         gr.Markdown("_Scan logs will appear here_")

            # RIGHT PANEL (Tasks)
            with gr.Column(scale=1):
                with gr.Accordion("Tasks & Actions", open=True):
                    gr.Markdown("## Tasks")
                    gr.Markdown("_AI-executable tasks will appear here_")
                    
                    with gr.Group():
                         gr.Button("Rescan All")
                         gr.Button("Export Report")
                         gr.Button("Clear Database", variant="stop")

        # --- Wiring ---
        scan_btn.click(
            on_scan, 
            inputs=[scan_input], 
            outputs=[scan_status, file_table]
        )
        
        search_btn.click(
            get_file_dataframe,
            inputs=[search_input],
            outputs=[file_table]
        )
        
        # Load initial data on load
        demo.load(load_recents, outputs=[file_table])
        
        # --- API Exposure ---
        # Note: Functions connected via .click() are auto-exposed as API endpoints
        # MCP server (GRADIO_MCP_SERVER=true) will pick these up automatically
        # TODO: Research gr.api() pattern for standalone function exposure in Gradio 6.0.2

    return demo

if __name__ == "__main__":
    demo = app_interface()
    demo.launch()
