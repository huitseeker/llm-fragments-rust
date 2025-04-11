import llm
import tempfile
import subprocess
import sys
import os
import json
import re
import html
from pathlib import Path


@llm.hookimpl
def register_fragment_loaders(register):
    register("rust", rust_loader)


def rust_loader(argument: str) -> llm.Fragment:
    crate_name = argument.split("@")[0] if "@" in argument else argument
    return llm.Fragment(
        rust_doc(argument),
        source=f"https://docs.rs/{crate_name}",
    )


def rust_doc(argument: str) -> str:
    crate_name = argument.split("@")[0] if "@" in argument else argument
    version = argument.split("@")[1] if "@" in argument else None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run = lambda cmd: subprocess.run(
            cmd, cwd=tmpdir, capture_output=True, check=True, text=True
        )
        try:
            # Create a minimal Cargo.toml
            cargo_toml = "[package]\nname = \"doc-fetcher\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\n"
            
            # Add the crate with specific version if provided
            if version:
                cargo_toml += f"{crate_name} = \"{version}\"\n"
            else:
                cargo_toml += f"{crate_name} = \"*\"\n"
                
            with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
                f.write(cargo_toml)
                
            # Create src directory with a basic main.rs that imports the crate
            os.mkdir(os.path.join(tmpdir, "src"))
            with open(os.path.join(tmpdir, "src", "main.rs"), "w") as f:
                f.write(f"""
// This file is used to generate documentation for {crate_name}
extern crate {crate_name};

fn main() {{
    // Empty main function
    println!("Documentation generator for {crate_name}");
}}
""")
            
            # Run cargo update to get the latest compatible version
            run(["cargo", "update"])
            
            # Generate docs
            run(["cargo", "doc", "--no-deps", "--document-private-items"])
            
            # Extract useful info from Cargo.lock to see which version was used
            try:
                with open(os.path.join(tmpdir, "Cargo.lock"), "r") as f:
                    cargo_lock = f.read()
                version_match = re.search(rf'name = "{crate_name}"[\s\S]*?version = "([^"]+)"', cargo_lock)
                resolved_version = version_match.group(1) if version_match else "unknown"
            except (FileNotFoundError, AttributeError):
                resolved_version = version or "latest"
            
            # First try: use cargo rustdoc to get module information
            module_info = []
            try:
                # Get cargo metadata to find dependencies
                metadata_result = run(["cargo", "metadata", "--format-version=1"])
                metadata = json.loads(metadata_result.stdout)
                
                # Find our crate in the dependencies
                dependencies = []
                for package in metadata.get("packages", []):
                    if package.get("name") == crate_name:
                        dependencies = package.get("dependencies", [])
                        break
                
                # Get documentation content
                html_doc_path = Path(tmpdir) / "target" / "doc" / crate_name / "index.html"
                if html_doc_path.exists():
                    with open(html_doc_path, "r") as f:
                        html_content = f.read()
                    
                    # Extract text content (basic approach)
                    text_content = html.unescape(re.sub(r'<[^>]+>', ' ', html_content))
                    text_content = re.sub(r'\s+', ' ', text_content).strip()
                    
                    # Extract crate documentation if available
                    doc_section_match = re.search(r'Crate\s+[^<>]+\s+Documentation(.*?)(?:Module|Struct|Trait|Enum|Type|Macro|Const|Static|Function|Derive)', text_content, re.DOTALL)
                    if doc_section_match:
                        module_info.append(f"# Crate Documentation\n\n{doc_section_match.group(1).strip()}\n")
                
                # Get information about what modules are available
                run(["cargo", "build"])
                
                # Use rustdoc to generate text docs 
                docs_dir = Path(tmpdir) / "target" / "doc"
                crate_docs = []
                
                # Try to find all documented modules and items
                for module_html in docs_dir.glob(f"{crate_name}/**/*.html"):
                    relative_path = module_html.relative_to(docs_dir / crate_name)
                    if str(relative_path) == "index.html":
                        continue
                        
                    module_name = str(relative_path).replace(".html", "").replace("/", "::")
                    if module_name.endswith("::index"):
                        module_name = module_name[:-7]
                    
                    crate_docs.append(f"- {module_name}")
                
                if crate_docs:
                    module_info.append("# Available Modules and Items\n\n" + "\n".join(sorted(crate_docs)))
                    
                # Run cargo tree to get dependency information
                tree_result = run(["cargo", "tree", "--edges", "features"])
                module_info.append(f"# Dependency Tree\n\n```\n{tree_result.stdout}\n```")
                
                # Collect examples if they exist
                example_path = docs_dir / crate_name / "examples"
                examples = []
                if Path(example_path).exists():
                    module_info.append("# Examples\n")
                    for example_html in example_path.glob("*.html"):
                        example_name = example_html.stem
                        with open(example_html, "r") as f:
                            example_content = f.read()
                            
                        # Extract example code (very basic approach)
                        code_blocks = re.findall(r'<pre>(.*?)</pre>', example_content, re.DOTALL)
                        if code_blocks:
                            examples.append(f"## {example_name}\n\n```rust\n{html.unescape(code_blocks[0])}\n```")
                    
                    if examples:
                        module_info.append("\n\n".join(examples))
                
            except subprocess.CalledProcessError as e:
                print(f"Error getting module information: {e}", file=sys.stderr)
                module_info.append(f"Failed to extract detailed module information: {e}")
            
            # Fallback: use cargo metadata if nothing else worked
            if not module_info:
                metadata_result = run(["cargo", "metadata", "--format-version=1"])
                metadata = json.loads(metadata_result.stdout)
                
                for package in metadata.get("packages", []):
                    if package.get("name") == crate_name:
                        package_info = [
                            f"# {package.get('name')} {package.get('version')}",
                            f"\n{package.get('description', 'No description available')}",
                            f"\n**Repository**: {package.get('repository', 'Not specified')}",
                            f"\n**License**: {package.get('license', 'Not specified')}",
                        ]
                        
                        # Add features if available
                        features = package.get("features", {})
                        if features:
                            package_info.append("\n\n## Features\n")
                            for feature, deps in features.items():
                                deps_str = ", ".join(deps) if deps else "No dependencies"
                                package_info.append(f"- **{feature}**: {deps_str}")
                        
                        # Add dependencies
                        deps = package.get("dependencies", [])
                        if deps:
                            package_info.append("\n\n## Dependencies\n")
                            for dep in deps:
                                dep_name = dep.get("name", "")
                                dep_req = dep.get("req", "")
                                package_info.append(f"- **{dep_name}**: {dep_req}")
                        
                        module_info = ["\n".join(package_info)]
                        break
            
            # Return a well-formatted document
            header = f"# {crate_name} (version {resolved_version})\n\nDocumentation for Rust crate: {crate_name}\n\n"
            return header + "\n\n".join(module_info)
            
        except subprocess.CalledProcessError as e:
            print(f"$ {' '.join(e.cmd)}", file=sys.stderr)
            print(e.stderr, file=sys.stderr)
            
            # Fallback to minimal info 
            try:
                # Try to get basic crate information from crates.io
                crates_io_url = f"https://crates.io/api/v1/crates/{crate_name}"
                curl_result = subprocess.run(
                    ["curl", "-s", crates_io_url],
                    capture_output=True, text=True
                )
                
                if curl_result.returncode == 0 and curl_result.stdout:
                    try:
                        crate_data = json.loads(curl_result.stdout)
                        crate_info = crate_data.get("crate", {})
                        
                        return f"""# {crate_name} (version {version or crate_info.get('max_version', 'latest')})

{crate_info.get('description', 'No description available')}

- **Created**: {crate_info.get('created_at', 'Unknown')}
- **Downloads**: {crate_info.get('downloads', 'Unknown')}
- **Homepage**: {crate_info.get('homepage', 'Not specified')}
- **Documentation**: {crate_info.get('documentation', 'Not specified')}
- **Repository**: {crate_info.get('repository', 'Not specified')}
- **License**: {crate_info.get('license', 'Not specified')}

Failed to generate detailed documentation for this crate.
"""
                    except json.JSONDecodeError:
                        pass
                
                # If crates.io API fails, return minimal information
                return f"""# {crate_name} (version {version or 'latest'})

Failed to generate detailed documentation for this crate.

For more information, visit:
- https://docs.rs/{crate_name}
- https://crates.io/crates/{crate_name}
"""
                
            except Exception as e2:
                print(f"Secondary error: {e2}", file=sys.stderr)
                return f"Failed to generate documentation for {crate_name} (version {version or 'latest'})."