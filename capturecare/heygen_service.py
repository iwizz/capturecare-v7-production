import requests
import logging
import time

logger = logging.getLogger(__name__)

class HeyGenService:
    """Service for generating AI avatar videos using HeyGen API"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.heygen.com"
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def get_avatars(self):
        """Fetch available avatars from HeyGen"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/avatars",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            avatars = data.get('data', {}).get('avatars', [])
            
            logger.info(f"Retrieved {len(avatars)} avatars from HeyGen")
            return avatars
            
        except Exception as e:
            logger.error(f"Error fetching HeyGen avatars: {e}")
            return []
    
    def get_voices(self, language=None):
        """Fetch available voices from HeyGen"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/voices",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            voices = data.get('data', {}).get('voices', [])
            
            # Log sample voices for debugging
            if voices and not language:
                sample_voice = voices[0]
                logger.info(f"Sample voice structure: name={sample_voice.get('name')}, language={sample_voice.get('language')}, languages={sample_voice.get('languages')}")
            
            # Filter by language if specified
            # Support multiple language field formats from HeyGen API
            if language:
                original_count = len(voices)
                filtered_voices = []
                
                for v in voices:
                    # Check 'language' field (string)
                    if v.get('language') and language.lower() in v.get('language', '').lower():
                        filtered_voices.append(v)
                        continue
                    
                    # Check 'languages' field (array)
                    if v.get('languages'):
                        if any(language.lower() in str(lang).lower() for lang in v.get('languages', [])):
                            filtered_voices.append(v)
                            continue
                    
                    # Check for language code (e.g., "en" for English)
                    lang_code_map = {
                        'english': 'en',
                        'spanish': 'es',
                        'french': 'fr',
                        'german': 'de',
                        'italian': 'it',
                        'portuguese': 'pt',
                        'chinese': 'zh',
                        'japanese': 'ja',
                        'korean': 'ko'
                    }
                    lang_code = lang_code_map.get(language.lower())
                    if lang_code:
                        if v.get('language') and lang_code in v.get('language', '').lower():
                            filtered_voices.append(v)
                            continue
                        if v.get('languages') and any(lang_code in str(lang).lower() for lang in v.get('languages', [])):
                            filtered_voices.append(v)
                            continue
                
                voices = filtered_voices
                logger.info(f"Retrieved {len(voices)} voices from HeyGen (filtered {original_count} for {language})")
            else:
                logger.info(f"Retrieved {len(voices)} voices from HeyGen (no filter)")
            
            return voices
            
        except Exception as e:
            logger.error(f"Error fetching HeyGen voices: {e}")
            return []
    
    def get_languages(self):
        """Fetch available voice languages/locales from HeyGen"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/voices",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            voices = data.get('data', {}).get('voices', [])
            
            # Extract unique languages from voices
            languages_set = set()
            for voice in voices:
                # Get language from different possible fields
                lang = voice.get('language')
                if lang:
                    languages_set.add(lang)
                
                # Also check for languages array
                langs_array = voice.get('languages', [])
                for l in langs_array:
                    if isinstance(l, str):
                        languages_set.add(l)
            
            # Convert to sorted list
            languages = sorted(list(languages_set))
            
            logger.info(f"Retrieved {len(languages)} unique languages from HeyGen")
            return languages
            
        except Exception as e:
            logger.error(f"Error fetching HeyGen languages: {e}")
            return []
    
    def generate_video(self, script, avatar_id=None, voice_id=None, voice_gender=None, 
                       voice_language="English", voice_speed=1.0, title="Health Report"):
        """
        Generate an AI avatar video from script
        
        Args:
            script: Text to be spoken (max 1500 characters)
            avatar_id: HeyGen avatar ID (if None, uses default)
            voice_id: HeyGen voice ID (if None, auto-selects based on gender/language)
            voice_gender: Preferred voice gender ("male" or "female")
            voice_language: Voice language (default: "English")
            voice_speed: Speech speed multiplier (default: 1.0)
            title: Video title
            
        Returns:
            dict with video_id and status, or None if error
        """
        try:
            # Truncate script if too long
            if len(script) > 1500:
                script = script[:1497] + "..."
                logger.warning("Script truncated to 1500 characters")
            
            # Auto-select voice if not provided
            if not voice_id:
                voices = self.get_voices(voice_language)
                
                # Filter by gender if specified
                if voice_gender and voices:
                    filtered = [v for v in voices if v.get('gender', '').lower() == voice_gender.lower()]
                    if filtered:
                        voices = filtered
                
                # Use first available voice
                if voices:
                    voice_id = voices[0].get('voice_id')
                    logger.info(f"Auto-selected voice: {voices[0].get('name')} ({voice_language}, {voices[0].get('gender')})")
                else:
                    logger.error("No suitable voice found")
                    return None
            
            # Use default avatar if not provided
            if not avatar_id:
                avatars = self.get_avatars()
                
                # Try to find a nurse/medical professional avatar
                medical_avatars = [a for a in avatars if 'nurse' in a.get('avatar_name', '').lower() 
                                   or 'doctor' in a.get('avatar_name', '').lower()
                                   or 'medical' in a.get('avatar_name', '').lower()]
                
                if medical_avatars:
                    avatar_id = medical_avatars[0].get('avatar_id')
                    logger.info(f"Auto-selected medical avatar: {medical_avatars[0].get('avatar_name')}")
                elif avatars:
                    avatar_id = avatars[0].get('avatar_id')
                    logger.info(f"Using default avatar: {avatars[0].get('avatar_name')}")
                else:
                    logger.error("No avatars available")
                    return None
            
            # Prepare video generation payload
            payload = {
                "video_inputs": [{
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal"
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": voice_id,
                        "speed": voice_speed
                    },
                    "background": {
                        "type": "color",
                        "value": "#FFFFFF"
                    }
                }],
                "dimension": {
                    "width": 1280,
                    "height": 720
                },
                "title": title,
                "test": False,
                "caption": True
            }
            
            # Generate video
            response = requests.post(
                f"{self.base_url}/v2/video/generate",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            video_id = result.get('data', {}).get('video_id')
            
            if video_id:
                logger.info(f"Video generation started: {video_id}")
                return {
                    'video_id': video_id,
                    'status': 'processing',
                    'message': 'Video generation in progress'
                }
            else:
                logger.error(f"No video_id in response: {result}")
                return None
                
        except requests.exceptions.HTTPError as e:
            logger.error(f"HeyGen API HTTP error: {e}")
            logger.error(f"Response content: {e.response.text if hasattr(e, 'response') else 'No response'}")
            return None
        except Exception as e:
            logger.error(f"Error generating HeyGen video: {e}")
            return None
    
    def get_video_status(self, video_id):
        """
        Check video generation status
        
        Args:
            video_id: HeyGen video ID
            
        Returns:
            dict with status and video_url (if completed)
        """
        try:
            response = requests.get(
                f"{self.base_url}/v1/video_status.get",
                params={"video_id": video_id},
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json().get('data', {})
            status = data.get('status')
            
            result = {
                'status': status,
                'video_id': video_id
            }
            
            if status == 'completed':
                result['video_url'] = data.get('video_url')
                result['thumbnail_url'] = data.get('thumbnail_url')
                logger.info(f"Video {video_id} completed: {result['video_url']}")
            elif status == 'failed':
                result['error'] = data.get('error', 'Video generation failed')
                logger.error(f"Video {video_id} failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking video status: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def wait_for_completion(self, video_id, max_wait_seconds=300, poll_interval=10):
        """
        Wait for video to complete (blocking)
        
        Args:
            video_id: HeyGen video ID
            max_wait_seconds: Maximum time to wait (default: 5 minutes)
            poll_interval: Seconds between status checks (default: 10)
            
        Returns:
            dict with final status and video_url (if successful)
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            result = self.get_video_status(video_id)
            status = result.get('status')
            
            if status == 'completed':
                return result
            elif status == 'failed' or status == 'error':
                return result
            
            logger.info(f"Video {video_id} still processing... ({int(time.time() - start_time)}s)")
            time.sleep(poll_interval)
        
        logger.warning(f"Video {video_id} timed out after {max_wait_seconds}s")
        return {
            'status': 'timeout',
            'error': f'Video generation exceeded {max_wait_seconds}s timeout'
        }
