# stage4_model_gen/groovae/run_groovae_subprocess.py
import subprocess
import os
import tempfile
import logging
from note_seq.protobuf import music_pb2

logger = logging.getLogger(__name__)

class GrooVAESubprocessRunner:
    """
    Wraps the GrooVAE execution in a subprocess call to support dual-environment setup.
    """
    def __init__(self, python_path: str, checkpoint_dir: str, config_name: str = "groovae_2bar_humanize"):
        self.python_path = python_path
        self.checkpoint_dir = checkpoint_dir
        self.config_name = config_name
        
        # Verify python path
        if not os.path.exists(self.python_path):
             logger.warning(f"Python executable not found at: {self.python_path}")

    def run(self, ns: music_pb2.NoteSequence, temperature: float = 1.0, seed: int = 42) -> music_pb2.NoteSequence:
        if not ns or not ns.notes:
            return ns

        # Locate the executor script relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        exec_script = os.path.join(current_dir, "groovae_exec.py")

        with tempfile.NamedTemporaryFile(suffix=".pb", delete=False) as tmp_in, \
             tempfile.NamedTemporaryFile(suffix=".pb", delete=False) as tmp_out:
            
            input_path = tmp_in.name
            output_path = tmp_out.name

        try:
            # Write input NS
            with open(input_path, "wb") as f:
                f.write(ns.SerializeToString())

            cmd = [
                self.python_path,
                exec_script,
                "--input_path", input_path,
                "--output_path", output_path,
                "--checkpoint_dir", self.checkpoint_dir,
                "--config_name", self.config_name,
                "--temperature", str(temperature),
                "--seed", str(seed)
            ]


            # Env vars to prevent TF freeze
            env = os.environ.copy()
            # Disable OneDNN optimization to prevent deadlock
            env["TF_ENABLE_ONEDNN_OPTS"] = "0"
            
            # FORCE CPU MODE for stability
            # GPU (RTX 3090) + TF 2.9 (Conda) is proving unstable/hanging.
            env["CUDA_VISIBLE_DEVICES"] = "-1" 
            env["OMP_NUM_THREADS"] = "1"
            env["KMP_BLOCKTIME"] = "0"
            
            # CRITICAL: Add conda lib directory to LD_LIBRARY_PATH (kept for safety)
            # python_path is typically .../envs/magenta_env/bin/python
            # we want .../envs/magenta_env/lib
            # bin_dir = os.path.dirname(self.python_path)
            # lib_dir = os.path.join(os.path.dirname(bin_dir), "lib")
            
            # current_ld = env.get("LD_LIBRARY_PATH", "")
            # env["LD_LIBRARY_PATH"] = f"{lib_dir}:{current_ld}"
            
            logger.info(f"Running GrooVAE subprocess: {' '.join(cmd)}")
            # logger.info(f"Subprocess LD_LIBRARY_PATH prefix: {lib_dir}")
            try:
                # Stream output directly to console
                subprocess.run(
                    cmd,
                    check=True,  # Raise CalledProcessError on failure
                    env=env
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"GrooVAE subprocess failed: {e}")
                raise RuntimeError(f"GrooVAE subprocess failed: {e}")

            # Read Output NS
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                out_ns = music_pb2.NoteSequence()
                with open(output_path, "rb") as f:
                    out_ns.ParseFromString(f.read())
                return out_ns
            else:
                 raise RuntimeError("GrooVAE subprocess created empty or missing output file.")

        finally:
            # Cleanup
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
