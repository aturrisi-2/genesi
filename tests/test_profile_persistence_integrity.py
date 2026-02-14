import json
from core.models.profile_model import UserProfile, Pet, Child


def test_profile_serialization_integrity(tmp_path):

    profile = UserProfile(
        name="Davide",
        profession="fotografo",
        pets=[Pet(type="dog", name="Rio")],
        children=[Child(name="Ennio"), Child(name="Zoe")]
    )

    data = profile.model_dump()

    # Must serialize
    json_string = json.dumps(data)

    # Must deserialize
    loaded = json.loads(json_string)

    # Must reconstruct without error
    UserProfile(**loaded)
