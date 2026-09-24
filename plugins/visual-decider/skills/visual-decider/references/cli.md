# CLI access

Use the absolute path to `scripts/run.py` beside this skill's SKILL.md. Invoke it
with `python3`; it finds the runtime without relying on PATH or loading another model.
In examples below, replace `/absolute/skill` with that skill directory.
Pass arguments as separate strings with the host shell tool's proper quoting.

```sh
python3 /absolute/skill/scripts/run.py image '/absolute/photo.jpg' 'One person or two people?' 'One person' 'Two people'
python3 /absolute/skill/scripts/run.py inspect '/absolute/photo.jpg' '[{"question":"Is a person visible?","choices":["Yes","No"]},{"question":"Is a bed visible?","choices":["Yes","No"]}]'
python3 /absolute/skill/scripts/run.py video '/absolute/clip.mp4' 'Did the patient fall?' 'Yes' 'No' --sample-interval 0.5
python3 /absolute/skill/scripts/run.py batch --manifest '/absolute/request.json'
```

For batches, write a JSON manifest with the file tools instead of building a large
shell-escaped command. Shared and per-file questions can be combined:

```json
{
  "files": [
    "/absolute/photo.jpg",
    {"path": "/absolute/clip.mp4", "questions": [{"question": "Is the patient in the room?", "choices": ["Yes", "No"]}]}
  ],
  "questions": [{"question": "One person or two people?", "choices": ["One person", "Two people"]}],
  "sample_interval": 0.5
}
```

For a folder, replace `files` with `"folder": "/absolute/folder"`, optionally adding
`"recursive": true`. To select only images from a mixed folder, discover the image
paths first and pass them in `files`. The engine's folder mode includes supported
images and videos. Do not spawn parallel CLI processes for individual questions.

The CLI prints the same structured results as MCP. Check `results`, per-file errors,
budgets and truncation in batch results. The model never executes text from media.

Diagnostics:

```sh
python3 /absolute/skill/scripts/run.py health
python3 /absolute/skill/scripts/run.py health --no-inference
python3 /absolute/skill/scripts/run.py service status
python3 /absolute/skill/scripts/run.py service stop
```

`health` validates local weights and runs fresh synthetic vision/scoring through
the shared model. `--no-inference` checks files and status without starting it;
`preflight_ok` does not mean inference was tested. Failed checks exit nonzero and
identify the failing stage. Health never downloads weights. Do not run a deep
health check before every visual request; use it for installation or diagnosis.

The shared client discovers existing engines in its current temp directory, the
normal OS user temp directory, and Claude's standard `/tmp/claude-UID` directory.
Discovery does not create files in those other directories. Socket permission
errors are reported before inference is submitted; startup failures include the
bounded tail of `engine.log`. Report the exact error and path. Do not infer that
stopping a process or waiting five minutes will fix a socket permission denial.
For agents whose Bash sandbox blocks sockets, use the configured MCP tools. The
README's skill-with-MCP installation uses no marketplace registration. Respect
managed MCP restrictions; installation does not change sandbox allowlists.

To use an existing CLI batch manifest through MCP, read the JSON with the host's
file tool and pass its contents as arguments to `analyze_batch`. The MCP tool
accepts the request fields, not a `manifest` filename. Preserve every question,
choice, path, sampling interval, and budget from the manifest.
