"""Generate local dependency inventory (NOT a lock file, nor full SBOM attestation)."""
from importlib import metadata
import json
from pathlib import Path
if __name__=='__main__':
 out=[{'name':d.metadata['Name'],'version':d.version} for d in metadata.distributions() if d.metadata.get('Name')]
 target=Path('DEPENDENCY_INVENTORY_LOCAL.json')
 target.write_text(json.dumps({'scope':'LOCAL_ENVIRONMENT_NOT_LOCKFILE','packages':sorted(out,key=lambda x:x['name'].lower())},indent=2),encoding='utf-8')
 print(target)
