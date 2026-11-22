"""Validate the transport-owned discovery receipt, read only and fail closed."""
import json,stat
from pathlib import Path
from stage4e_d2i_1.common import ContractError,require,digest,sha

def _object(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate metadata receipt key: '+key)
        result[key]=value
    return result

def _constant(value):
    raise ContractError('Nonfinite JSON constant in metadata receipt: '+value)

def validate_metadata_receipt(directory,discovered):
    """Never create, overwrite, delete, rename or repair runtime_metadata.json.

    The exclusive attempt directory is created by the existing collector.
    Discovery must supply exactly this regular, non-link JSON receipt.
    """
    directory=Path(directory);path=directory/'runtime_metadata.json'
    require(path.exists(),'Missing transport-owned runtime_metadata.json receipt')
    require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode),
        'Unexpected metadata receipt: regular non-link file required')
    require(path.resolve().parent==directory.resolve(),'Metadata receipt escapes attempt directory')
    try:
        content=path.read_text(encoding='utf-8')
        stored=json.loads(content,object_pairs_hook=_object,parse_constant=_constant)
    except (ValueError,UnicodeError) as exc:
        raise ContractError('Malformed transport-owned metadata receipt') from exc
    require(type(stored) is dict and type(discovered) is dict,'Unexpected metadata receipt root; object required')
    require(digest(stored)==digest(discovered),'Transport metadata receipt conflicts with discovered metadata')
    return {'status':'VERIFIED_TRANSPORT_RECEIPT','path':'runtime_metadata.json',
        'sha256':sha(path),'canonical_metadata_sha256':digest(discovered),
        'owner':'UNCHANGED_REAL_TRANSPORT_DISCOVERY','collector_receipt_writes':0,
        'collector_receipt_deletions':0,'missing_receipt_policy':'FAIL_NO_FALLBACK',
        'comparison':'STRICT_CANONICAL_JSON_WITH_DUPLICATE_NONFINITE_AND_TYPE_REJECTION'}
