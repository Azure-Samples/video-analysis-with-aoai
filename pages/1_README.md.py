import streamlit as st
import os

def show_readme():
    st.title("Video Analysis with GPT-4o - Documentation")
    
    # Find the root directory of the project by going up one level from the pages directory
    root_dir = os.path.dirname(os.path.dirname(__file__))
    readme_path = os.path.join(root_dir, "README.md")
    
    try:
        # Read the README.md file
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
            
        # Display the content using Streamlit's markdown
        st.markdown(readme_content)
        
        # Option to download the README file
        with open(readme_path, "rb") as file:
            btn = st.download_button(
                label="Download README.md",
                data=file,
                file_name="README.md",
                mime="text/markdown"
            )
            
    except FileNotFoundError:
        st.error("README.md file not found in the project root directory.")
    except Exception as e:
        st.error(f"Error reading README file: {str(e)}")

# If this file is run directly with streamlit run
if __name__ == "__main__":
    show_readme()
