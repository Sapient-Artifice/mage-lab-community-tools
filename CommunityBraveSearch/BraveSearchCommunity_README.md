# Brave Search Community Tool

A Brave Search tool that talks directly to Brave’s REST API.

### How It Works
Brave provides access to their search services programmatically through an API - provided you have an account and API key.

The default Brave search tool we provide in the app route these search requests through our gateway - provided you are signed into your mage lab account and have a positive balance. When using our gateway, web searches are not expensive (~$0.003/search), but they are also not free. 

For users who do not need a large number of searches per month, and are satisfied with the one query/second rate limit, you can [create your own account](https://api-dashboard.search.brave.com/app/plans) and use their free tier.

This document walks you through how to set up your own Brave search tool - after you have made an account with Brave and generated an API key.

#### Configuration
Once you have created your account with Brave and generated your API key:
- Modify the mage lab configuration to make the API key safely accessible by adding 
  - ```BRAVE_SEARCH_API_KEY="<your_API_key_here>"```
  - This should be added as a new line   
- You can access your configuration file in one of two ways, either
   - a) in the mage lab app: Settings -> Paths subpanel -> edit configuration file, or  
   - b) via a general text editor - it's located in ~/.config/magelab
- Alternatively, you can also pass `brave_api_key` to the functions directly when calling.

#### Tool Placement
- Place the BraveSearchCommunity.py tool into your ~/Mage/Tools folder and restart the application. 
- Upon restart, it should then be present in the Settings -> Tool Scope subpanel.
   - ***Toggle the new tool on and the old tool off to avoid conflict*** 
- Once the new tool has been toggled on it should work. 
If it does not, look for error messages in ~/.config/magelab/magelog 

#### Function Syntax
- `search_web_community(query: str, num_results: int = 1, brave_api_key: Optional[str] = None) -> str`
- `search_images_community(query: str, num_results: int = 1, brave_api_key: Optional[str] = None) -> str`

#### Details regarding how the Brave API works
- Endpoints used:
  - Web: `https://api.search.brave.com/res/v1/web/search`
  - Images: `https://api.search.brave.com/res/v1/images/search`
- Auth header: `X-Subscription-Token: <your_api_key>`
- Returns concise, Markdown-formatted results with titles, snippets, and URLs.



#### License
- This tool inherits the MIT License from the mage lab Community Tools repository.

Enjoy!
