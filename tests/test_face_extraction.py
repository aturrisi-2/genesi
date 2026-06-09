import pytest
import os
import core.llm_service
from unittest.mock import patch, AsyncMock
from core.face_memory_service import try_extract_faces_from_text

@pytest.mark.asyncio
async def test_extract_faces_from_text_success():
    # 1. Create a dummy image file
    tmp_img = "tests/dummy_face_image.jpg"
    os.makedirs("tests", exist_ok=True)
    with open(tmp_img, "wb") as f:
        f.write(b"dummy")

    # 2. Setup mock for LLM returning a valid JSON
    with patch("core.llm_service.llm_service._call_model", new_callable=AsyncMock) as mock_call_model:
        mock_call_model.return_value = '```json\n[{"name": "Mariella", "position_index": 0}, {"name": "Ennio", "position_index": 2}]\n```'
        
        # 3. Setup mock for save_known_face so we don't actually write to DB during unit test
        with patch("core.face_memory_service.save_known_face", new_callable=AsyncMock) as mock_save_face:
            
            # Action
            text = "Il primo a sinistra è Mariella, e l'ultimo a destra è Ennio."
            desc_img = "[UNKNOWN_FACES_DETECTED] Ci sono 3 persone nella foto."
            session_uid = "test_user_123"
            
            success = await try_extract_faces_from_text(text, tmp_img, desc_img, session_uid)
            
            # Assertions
            assert success is True
            mock_call_model.assert_called_once()
            assert mock_save_face.call_count == 2
            
            # Extract arguments from mock calls
            args1 = mock_save_face.call_args_list[0][0]
            args2 = mock_save_face.call_args_list[1][0]
            
            assert args1[0] == "Mariella"
            assert args1[2] == "[INDEX:0]"
            
            assert args2[0] == "Ennio"
            assert args2[2] == "[INDEX:2]"

    # Cleanup
    if os.path.exists(tmp_img):
        os.remove(tmp_img)

@pytest.mark.asyncio
async def test_extract_faces_from_text_empty():
    tmp_img = "tests/dummy_face_image2.jpg"
    os.makedirs("tests", exist_ok=True)
    with open(tmp_img, "wb") as f:
        f.write(b"dummy")

    with patch("core.llm_service.llm_service._call_model", new_callable=AsyncMock) as mock_call_model:
        # LLM returns empty array if it thinks the user isn't talking about faces
        mock_call_model.return_value = '[]'
        
        with patch("core.face_memory_service.save_known_face", new_callable=AsyncMock) as mock_save_face:
            success = await try_extract_faces_from_text("Che bella foto!", tmp_img, "Desc", "uid")
            
            assert success is False
            assert mock_save_face.call_count == 0
            
    # Cleanup
    if os.path.exists(tmp_img):
        os.remove(tmp_img)
