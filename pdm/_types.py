from typing import Dict, List, Tuple, Union

Source = Dict[str, Union[str, bool]]
RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]
SearchResult = List[Dict[str, Union[str, List[str]]]]
