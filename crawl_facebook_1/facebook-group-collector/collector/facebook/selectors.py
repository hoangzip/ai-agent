"""
collector/facebook/selectors.py — ALL Facebook DOM selectors in one place.

IMPORTANT: This is the ONLY file that should contain CSS selectors or XPath.
When Facebook changes its DOM structure, update ONLY this file.
Do NOT scatter selectors across other modules.

Phase 02: File created with structure; selectors are placeholders.
Phase 04: Real selectors will be discovered and filled in.

Naming convention:
  FEED_*      — selectors for the group feed / post list
  POST_*      — selectors for individual post pages
  COMMENT_*   — selectors for comments section
  AUTH_*      — selectors for auth state detection
  ACTOR_*     — selectors for user/actor information
"""
from __future__ import annotations


class GroupSelectors:
    """Selectors for group header and metadata."""
    # Group title/name
    GROUP_NAME = (
        "div[data-pagelet='GroupHeading'] h1, "
        "div[role='main'] h1, "
        "h1[dir='auto'], "
        "h1"
    )
    # Group privacy & member text container
    HEADER_INFO = (
        "div[data-pagelet='GroupHeading'] span, "
        "div[role='main'] div[dir='auto'] span"
    )
    # Member count link or text
    MEMBERS_LINK = "a[href*='/members/'], a[href*='/membership/']"
    # Group description
    DESCRIPTION = "div[data-pagelet='GroupAbout'] div[dir='auto'], div[aria-label*='About']"


class FeedSelectors:
    """Selectors for the group feed page."""
    # Feed container
    FEED_CONTAINER = "div[role='feed']"
    # Post cards inside feed
    POST_ITEMS = (
        "div[role='feed'] > div[data-pagelet*='FeedUnit'], "
        "div[role='feed'] > div[role='article'], "
        "div[role='feed'] > div"
    )
    # Post permalinks (timestamp link or permalink)
    POST_LINK = (
        "a[href*='/groups/'][href*='/posts/'], "
        "a[href*='/groups/'][href*='/permalink/'], "
        "a[href*='/permalink.php?story_fbid=']"
    )
    # Author name and link
    AUTHOR_NAME = "h3 a[role='link'], h2 a[role='link'], a[role='link'][href*='/user/'] strong, a[role='link'][href*='profile.php'] strong, a[role='link'][href*='/user/'] span, a[role='link'][href*='profile.php'] span"
    AUTHOR_PROFILE_LINK = (
        "h3 a[href*='facebook.com'], "
        "h2 a[href*='facebook.com'], "
        "h3 a[role='link'], "
        "h2 a[role='link'], "
        "a[role='link'][href*='facebook.com/profile.php'], "
        "a[role='link'][href*='/user/']"
    )
    # Post timestamp element
    TIMESTAMP = (
        "abbr[data-utime], span[data-utime], "
        "a[href*='/posts/'], a[href*='/permalink/'], a[href*='story_fbid=']"
    )
    # Post message / content text in feed card
    CONTENT_PREVIEW = (
        "div[data-ad-preview='message'], "
        "div[data-ad-comet-preview='message'], "
        "div[dir='auto'][style*='text-align']"
    )
    # Comment count button or text
    COMMENT_COUNT = (
        "div[role='button']:has-text('bình luận'), "
        "div[role='button']:has-text('comments'), "
        "span:has-text('bình luận'), "
        "span:has-text('comments'), "
        "a[href*='comment']"
    )
    # Media / images in feed card (only genuine post content photos, not icons/sidebar)
    FEED_IMAGES = (
        "a[href*='/photo/'] img, "
        "a[href*='/photo.php'] img, "
        "a[href*='/photos/'] img, "
        "div[data-visualcompletion='media-vc-image'] img, "
        "div[data-ad-preview='message'] ~ div img"
    )
    # "Load more" or end-of-feed marker
    END_OF_FEED_MARKER = "[data-end-of-feed='true']"


class PostSelectors:
    """Selectors for individual post detail pages."""
    # Main post content area
    POST_CONTENT = "[data-pagelet='MainFeed'] > div, article"
    # Full post text
    POST_TEXT = "div[data-ad-preview='message'], [data-ad-comet-preview='message']"
    # Post title (if group post has a title)
    POST_TITLE = "h1, [role='heading'][aria-level='1']"
    # Posted timestamp on post page
    POST_TIMESTAMP = "abbr[data-utime]"
    # Post images (full size)
    POST_IMAGES = "div[data-visualcompletion='media-vc-image'] img"


class CommentSelectors:
    """Selectors for comments and replies on post detail pages."""
    # Top-level comment items
    TOP_LEVEL_COMMENTS = (
        "div[role='article'], "
        "div[aria-label*='Bình luận của'], "
        "div[aria-label*='Comment by'], "
        "div[aria-label*='Comment'] > ul > li"
    )
    # Comment text / content
    COMMENT_TEXT = (
        "div[dir='auto'][style*='text-align'], "
        "div[dir='auto'] span[dir='auto'], "
        "div[lang], "
        "[data-ad-preview='message']"
    )
    # Comment author name
    COMMENT_AUTHOR = (
        "a[role='link'] > span > span, "
        "a[role='link'] strong, "
        "span > a[role='link'], "
        "h3 a, span[class*='author']"
    )
    # Comment author profile link
    COMMENT_AUTHOR_LINK = (
        "a[role='link'][href*='facebook.com/profile.php'], "
        "a[role='link'][href*='/user/'], "
        "a[role='link'][href*='facebook.com'], "
        "h3 a[href*='facebook.com']"
    )
    # Comment timestamp or permalink
    COMMENT_TIMESTAMP = (
        "a[href*='comment_id'], "
        "abbr[data-utime], "
        "span[data-utime], "
        "a[role='link'] > span"
    )
    # Reply container inside a comment thread
    REPLIES_CONTAINER = "ul, div[role='group']"
    # Individual reply items
    REPLY_ITEMS = (
        "div[role='article'], "
        "li[data-sigil='comment-inline-reply']"
    )
    # "View more comments" button
    LOAD_MORE_COMMENTS = (
        "span:has-text('Xem thêm bình luận'), "
        "span:has-text('View more comments'), "
        "div[role='button']:has-text('Xem thêm bình luận'), "
        "div[role='button']:has-text('View more comments'), "
        "div[data-sigil='ajaxify'][href*='comment']"
    )
    # "View X replies" button
    VIEW_REPLIES_BUTTON = (
        "span:has-text('phản hồi'), "
        "span:has-text('replies'), "
        "span:has-text('trả lời'), "
        "div[role='button']:has-text('phản hồi'), "
        "div[role='button']:has-text('replies'), "
        "div[data-sigil='replies-see-all']"
    )
    # Comment count shown in UI
    COMMENT_COUNT_BADGE = "span[data-sigil='comment-count']"


class AuthSelectors:
    """Selectors for authentication state detection."""
    # Login form (indicates session expired)
    # Full-page login form (NOT sidebar/embedded forms)
    # Use :not to exclude forms nested inside sidebars or non-primary containers
    LOGIN_FORM = "form[action*='/login/device-based'], form#login_form"
    # Login inputs
    EMAIL_INPUT = "input#email, input[name='email']"
    PASSWORD_INPUT = "input#pass, input[name='pass']"
    # Login button
    LOGIN_BUTTON = "button[name='login'], button[type='submit'], [role='button'][name*='Log In'], [role='button'][name*='Đăng nhập']"
    # Facebook checkpoint indicator
    CHECKPOINT_INDICATOR = "form[action*='checkpoint'], div[id*='checkpoint']"
    # MFA/2FA prompt
    MFA_PROMPT = "form[action*='two_step'], input#approvals_code, input[name='approvals_code']"
    # Logged-in indicators — includes group feed and navigation
    LOGGED_IN_INDICATOR = (
        "div[aria-label*='Your profile'], "
        "div[aria-label*='Trang cá nhân'], "
        "div[aria-label*='Menu Facebook'], "
        "svg[aria-label*='Trang cá nhân'], "
        "a[href*='/me/']"
    )


class ActorSelectors:
    """Selectors for extracting user/actor information."""
    # Profile link in post header
    PROFILE_LINK = "h3 > span > a, h2 > span > a"
    # Display name
    DISPLAY_NAME = "h3 > span > a > span, h2 > span > a > span"
    # Avatar image (may contain user ID in src)
    AVATAR_IMAGE = "image[xlink:href], img[data-imgperflogname='profileCoverPhoto']"


# ---------------------------------------------------------------------------
# Validation helper (used in Phase 04)
# ---------------------------------------------------------------------------

def validate_selector_not_empty(name: str, value: str) -> None:
    """Assert selector is not an empty string (guard against accidental blanks)."""
    if not value or not value.strip():
        raise ValueError(f"Selector {name!r} is empty — update selectors.py")
