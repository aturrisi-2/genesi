import json
from core.models.profile_model import UserProfile, Pet, Child
from core.identity_extractor import IdentityUpdate, merge_identity_update


def test_profile_serialization_integrity(tmp_path):

    profile = UserProfile(
        name="Davide",
        profession="fotografo",
        pets=[Pet(type="dog", name="Rio")],
        children=[Child(name="Ennio"), Child(name="Zoe")]
    )

    data = profile.model_dump(mode="json")

    # Must serialize
    json_string = json.dumps(data)

    # Must deserialize
    loaded = json.loads(json_string)

    # Must reconstruct without error
    UserProfile(**loaded)


def test_profile_with_identity_fields():
    profile = UserProfile(
        name="Davide",
        interests=["musica elettronica"],
        preferences=["lavorare di notte"],
        traits=["introverso"]
    )

    data = profile.model_dump(mode="json")
    json_string = json.dumps(data)
    loaded = json.loads(json_string)
    reconstructed = UserProfile(**loaded)

    assert "musica elettronica" in reconstructed.interests
    assert "lavorare di notte" in reconstructed.preferences
    assert "introverso" in reconstructed.traits
    assert len(data.keys() - {"name", "profession", "spouse", "pets", "children",
                               "interests", "preferences", "traits", "updated_at"}) == 0


def test_identity_merge_deduplication():
    profile = UserProfile(
        interests=["musica elettronica"]
    )

    update = IdentityUpdate(
        interests=["musica elettronica", "fotografia"],
        preferences=["lavorare di notte"],
        traits=[]
    )

    merge_identity_update(profile, update)

    assert profile.interests == ["musica elettronica", "fotografia"]
    assert profile.preferences == ["lavorare di notte"]
    assert profile.traits == []

    # Verify JSON roundtrip
    data = profile.model_dump(mode="json")
    json_string = json.dumps(data)
    loaded = json.loads(json_string)
    UserProfile(**loaded)
