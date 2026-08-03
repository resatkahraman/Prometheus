import fnmatch
from pathlib import PurePosixPath
from typing import Any
from app.agents.models import AgentProfile
from app.tools.base import ToolError

PATH_TOOLS={"workspace_list","workspace_read","workspace_search","workspace_write","git_diff"}
WRITE_TOOLS={"workspace_write"}

def normalize(value:Any)->str:
    text=str(value if value is not None else '.').strip().replace('\\','/') or '.'
    path=PurePosixPath(text)
    if path.is_absolute() or '..' in path.parts: raise ToolError('Workspace dışı yol kullanılamaz.')
    value=path.as_posix()
    return '.' if value in {'','.'} else value.lstrip('./')

def matches(path:str, patterns:list[str])->bool:
    candidate='' if path=='.' else path
    for raw in patterns:
        pat=raw.strip().replace('\\','/').lstrip('./')
        if pat in {'','*','**'}: return True
        if pat.endswith('/**'):
            prefix=pat[:-3].rstrip('/')
            if candidate==prefix or candidate.startswith(prefix+'/'): return True
        if fnmatch.fnmatchcase(candidate,pat): return True
        if pat.startswith('**/') and fnmatch.fnmatchcase(candidate,pat[3:]): return True
    return False

class AgentAccessController:
    def authorize(self, *, profile:AgentProfile, tool_name:str, arguments:dict[str,Any])->None:
        if tool_name not in profile.allowed_tools:
            raise ToolError(f"{profile.name} agentının '{tool_name}' aracını kullanma yetkisi yok.")
        if tool_name in WRITE_TOOLS and profile.read_only:
            raise ToolError(f"{profile.name} salt okunur bir agenttır; dosya yazamaz.")
        if tool_name not in PATH_TOOLS: return
        path=normalize(arguments.get('path','.'))
        scopes=profile.write_paths if tool_name in WRITE_TOOLS else profile.read_paths
        if not matches(path,scopes):
            kind='yazamaz' if tool_name in WRITE_TOOLS else 'okuyamaz'
            raise ToolError(f"{profile.name} '{path}' yolunu {kind}. İzinli kapsam: {', '.join(scopes) or 'yok'}")
