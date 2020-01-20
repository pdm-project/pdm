from typing import Dict, Union, Tuple, List

Source = Dict[str, Union[str, bool]]
RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]
