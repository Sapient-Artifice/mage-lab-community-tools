# MAGE LAB DOCUMENTATION
v0.8.0
---

### introduction
Welcome to mage lab, a desktop application that provides an interface for you, your computer, and your AI tools to work together efficiently. By simply talking to mage, you can open files, browse the web, play or view media like audio, images, or videos,  edit documents, or even create entire projects. Mage can also read websites and files (upon request). This all comes out of the box when using supported language models, including voice integration as a first class citizen. Talking or typing are both part of the same chat flow.


The core functionality of mage lab will be sufficient for many basic use cases. From there, mage has been designed to allow for easy customization to suit your specific needs. This is where the power of mage lab becomes self evident, having the ability to modify or expand mage's capabilities on the fly to be exactly what you need it to be, dynamically.

**core functionality includes**

- Live language model hot swapping in context
- Adding new models into your environment
- The ability to blend local and remote model usage into the same workflows
- The ability to integrate custom functionality directly into the system and interface
- A suite of core tools available that include
    - Searching the web
    - Opening links and files
    - Writing new files
    - Reading websites and files
    - Searching for folders and files
    - Math calculations and Python shell access
    - Navigating directories

Mage will easily use these tools to help you with what you are working on, sometimes without even asking for them directly. That said, mage only knows what you tell it, and can only use tools that are enabled in the settings. Tools that are not toggled on will not be available for use during that session.

In addition to the functionality mentioned above, mage lab is an effective way to tie your AI tools directly to your physical devices and infrastructure. The system boasts a very strong and cost effective performance with supported open source and proprietary AI models alike. mage lab prioritizes privacy, transparency, and simplicity.

mage lab can use AI to reason through complex tasks while using tools at the same time, which is incredibly powerful. These abilities will continue to scale and impress as LLMs mature.

## FIRST TIME USERS

### quick start feature guide

Please consider mage lab as your one easy studio for interacting with AI tools, naturally using both voice and text, while accessing computer features together. You can even interrupt a chat, just like in a human conversation!

### installation

For general users, our consumer installers provide a direct path to installing mage lab on your computer without the need for any technical know-how. Just click your way through the guided process and double click the application icon to launch after installed.

### getting started

To begin, mage lab must be connected to the models you want to use. To help you get started, we offer a gateway with a selection of models from the top providers. To access the gateway, simply sign in using your gmail to create an account - we do not see your gmail password. 
Your account will initialize with a small amount of credit so you can try things out immediately. If you choose to add funds to your account, additional models will become available. 
If you do not want to use the mage lab gateway, you can configure most remote and/or local providers through the Settings.

#### chatting: text & voice

Unified Inputs: You can talk to mage and/or type your commands interchangeably. To use your voice, simply hold down the "Hold to Talk" <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
        <path d="M12 1C10.346 1 9 2.346 9 4v6c0 1.654 1.346 3 3 3s3-1.346 3-3V4c0-1.654-1.346-3-3-3z"/>
        <path d="M19 10v2c0 3.866-3.134 7-7 7s-7-3.134-7-7v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/>
        <line x1="8" y1="23" x2="16" y2="23"/> </svg> button. Mage will listen while holding and then transcribe and respond when you release the button.

#### chatting: hands-free

Voice Activity Detection: Experience hands-free communication with mage! Toggle voice activity detection using  <svg viewBox="0 0 24 24" fill="#4285f4" stroke="none" style="width:0.9em; height:0.9em;">
        <circle cx="12" cy="12" r="8"></circle></svg> for a seamless interaction. mage will listen continuously and will only transcribe and respond after detecting a pause in your speech.

#### interrupting / mute

You can interrupt mage by clicking the "Hold to Talk" <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
        <path d="M12 1C10.346 1 9 2.346 9 4v6c0 1.654 1.346 3 3 3s3-1.346 3-3V4c0-1.654-1.346-3-3-3z"/>
        <path d="M19 10v2c0 3.866-3.134 7-7 7s-7-3.134-7-7v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/>
        <line x1="8" y1="23" x2="16" y2="23"/>
    </svg> button quickly to stop its speech or continue holding the button down to interrupt and send a new message. To mute mage speaking entirely, press the mute <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M4 8h4l5-4v16l-5-4H4z"></path>
    <path d="M15 8c1.5 1.5 1.5 6 0 7.5"></path>
    <path d="M18 5c2 2 2 10 0 12"></path>
</svg> toggle to switch off AI speech in the header bar     <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
            <path d="M4 8h4l5-4v16l-5-4H4z"></path>
            <line x1="19" y1="9" x2="15" y2="13"></line>
            <line x1="15" y1="9" x2="19" y2="15"></line>
        </svg>. You can still talk, but mage will only respond with text. When muted, the text to speech model does not run.

#### stop

<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"
style="width:1em;height:1em;">
<rect x="5" y="5" width="14" height="14" />
</svg> Use to stop an erroneous message, or tool sequence after it's begun processing. 
Note: for python and bash processes running at the system level, this stop will not terminate them at this time.


#### ai response time

Response times can vary depending on the LLM or setup you are using and the complexity of the  task. Using custom tools with their own limitations can affect the time it takes for task completion. 

### ui capabilities

This section is designed to familiarize you with the user interface and help you make the most of mage lab's interactive features.

#### core concepts & features

mage is always operating out of some specific directory on your computer (default defined by the Settings Workspace path). This is where mage will save things you create, and look for things you ask for by default, if not otherwise specified. If you want mage to work in a specific project directory, you can just ask mage to move there.

##### ui canvas elements

 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M3 9l9-6 9 6v11a2 2 0 0 1-2 2H5
            a2 2 0 0 1-2-2z"></path>
    <polyline points="9 22 9 12 15 12 15 22"></polyline>
</svg>  home view 
 
 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M3 7H9l1.5 2H21v11
            a2 2 0 0 1-2 2H3
            a2 2 0 0 1-2-2V9
            a2 2 0 0 1 2-2z"></path>
</svg>  open file browser 
 
 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
</svg>  close all tabs 
 
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <circle cx="12" cy="12" r="5"></circle>
    <line x1="12" y1="1" x2="12" y2="3"></line>
    <line x1="12" y1="21" x2="12" y2="23"></line>
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
    <line x1="1" y1="12" x2="3" y2="12"></line>
    <line x1="21" y1="12" x2="23" y2="12"></line>
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
</svg> /
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
        <path d="M12 3a6.364 6.364 0 0 0 9 9 9 9 0 1 1-9-9z"/>
        <path d="M19 3v4" opacity="0.2"/>
        <path d="M21 7h-4" opacity="0.2"/>
        <path d="M12 21v-1" opacity="0.2"/>
        <path d="M7 16l-1 1" opacity="0.2"/>
    </svg> toggle dark/light mode
 
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <rect x="3" y="3" width="7" height="7"></rect>
    <rect x="14" y="3" width="7" height="7"></rect>
    <rect x="14" y="14" width="7" height="7"></rect>
    <rect x="3" y="14" width="7" height="7"></rect>
</svg>  toggle vertical / side by side layout 
 
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M4 8h4l5-4v16l-5-4H4z"></path>
    <path d="M15 8c1.5 1.5 1.5 6 0 7.5"></path>
    <path d="M18 5c2 2 2 10 0 12"></path>
</svg>  mute / volume 
 
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z"></path>
    <line x1="12" y1="7" x2="12" y2="13"></line>
    <line x1="9" y1="10" x2="15" y2="10"></line>
</svg>  start new chat 
 
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <circle cx="12" cy="12" r="3"></circle>
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33
    1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2h-.12a2 2 0 01-2-2v-.09a1.65 1.65 0 00-1-1.51
    1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82
    1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2v-.12a2 2 0 012-2h.09
    a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2
    2 0 012.83-2.83l.06.06a1.65 1.65 0 001.82.33h.09
    a1.65 1.65 0 001-1.51V3a2 2 0 012-2h.12a2 2 0 012 2v.09
    a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06
    a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v.09
    a1.65 1.65 0 001.51 1H21a2 2 0 012 2v.12a2 2 0 01-2 2h-.09
    a1.65 1.65 0 00-1.51 1z"></path>
</svg>  open settings panel 
 
<svg viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
  <circle cx="11" cy="11" r="7"/>
  <line x1="16" y1="16" x2="21" y2="21"/>
</svg>  open chat explorer

##### canvas layouts

<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <rect x="3" y="3" width="7" height="7"></rect>
    <rect x="14" y="3" width="7" height="7"></rect>
    <rect x="14" y="14" width="7" height="7"></rect>
    <rect x="3" y="14" width="7" height="7"></rect>
</svg> 
 The default canvas displays bubbles and windows in a "side-by-side" view (chats on one side, while tabs on the other). You can toggle the layout button to switch to a "vertical" view (tabs on top, and chats on bottom).

##### mage's tabs

Mage lab allows you to open various file types as tabs within its user interface (UI). You can open these files manually with the file picker or just ask mage to do it!

 Text Editor: Create and edit documents with ease
 Image Gallery: View and manage images directly within the interface
 Video Player: Watch videos without leaving the application
 Audio Player: Listen to audio files seamlessly
 PDF Editor: Reader and basic editing 
 CSV Viewer: Formats and adds basic search

You can easily open files, write files, and view media in the UI. Mage can help you open links and browse and read the web right from mage lab without lifting a finger.

If mage writes a file, mage will display it for you in a new tab in the UI, letting you track changes in real time and helping you maintain control over your work. 

** Opening a tab doesn't mean the AI model reads the content.** You have to ask mage to explicitly read it. While mage serves as a supportive tool, it grounds the experience so that you are always in charge of your tasks and decisions!

##### media types

You can open tabs automatically by asking mage,  or manually using the file explorer <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
    <path d="M3 7H9l1.5 2H21v11
            a2 2 0 0 1-2 2H3
            a2 2 0 0 1-2-2V9
            a2 2 0 0 1 2-2z"></path>
</svg> (in the header bar). Generally speaking, the tabs operate independent of the languange models context - though they can be integrated by the tool developer, if desired. However, for our core tools opening a tab is kept independent of llm context loading without an additional user request for the model to explicitly read it.

**Current file types supported**

Text file types
       
     pdf, md, txt, csv, html, and most common code extensions

Audio file types
       
     mp3, wav, flac

Image file types
       
     png, jpg, webp, gif,  bmp, svg

Video file types
       
     mp4

More file types will be supported over time. If there is something important to you not currently supported, let us know.

#### drag and drop files onto the canvas

Drag and drop workspace imports: You can drop supported file types directly into the mage lab app to open them in a tab.

#### tools

mage accomplishes task execution through the use of tools. Tool use in mage lab is explicit and all tools are available for configuration in the settings panel. You can see exactly what they do there and which ones are active. All tools run locally. Ideally, tool use should be 'invisible', for example if you ask mage to "read a file" it should just do it without having to say "use the read file tool". Sometimes you can give mage a nudge if you have to. Results will vary between LLMs.

mage lab can use tools that might not provide visual feedback in the UI. 

All tools are clearly visible and completely under your control in the configuration settings. This means you can easily customize which tools you want to use, ensuring that your workspace is tailored to your preferences. With this clear visibility and control, you can enhance your productivity without unnecessary distractions or overloaded context by controlling the tool scope.

#### chat explorer

<svg viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
  <circle cx="11" cy="11" r="7"/>
  <line x1="16" y1="16" x2="21" y2="21"/>
</svg> When you open the chat explorer it indexes all chats stored in your assigned chat path and allows collective search, navigation, aggregation, context construction, and export capabilities. Note: mage is not able to use the tool directly through a prompt at this time.

Once indexed, you will have a full scroll-able list of your content.  
You can also toggle the additional tool messages on of off in this view, like in the primary canvas. 
If you enter a search term the interface will change and all mentions of that phrase will show up as independent blocks. Each block can be explored using the following interface UI elements 

**chat explorer ui elements**

   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"
       style="width:1em; height:1em;">
       <path d="M19 21H5a2 2 0 0 1-2-2V5
               a2 2 0 0 1 2-2h11l5 5v11
               a2 2 0 0 1-2 2z"/>
       <polyline points="17 21 17 13 7 13 7 21"/>
       <polyline points="7 3 7 8 15 8"/>
   </svg>  Save the aggregated result from all blocks to a single json output file

   +/-  expand/collapse the chat bubbles above and below 

   i  provides an information card that includes basic information about that specific chat file, a way to return to that chat, and a means to open the raw file

   ↑  export that chat block to json output file

   ↓  insert that chat block into the main canvas chat window

   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:0.9em; height:0.9em;">
     <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z"/>
     <line x1="12" y1="7" x2="12" y2="13"/>
     <line x1="9" y1="10" x2="15" y2="10"/>
   </svg>  fork the conversation from that chat bubble 

   <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
     <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
     <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
   </svg>  copy that chat block


### data privacy

mage lab respects your data privacy and freedom. We do not save or track any of your conversations or personal data. When using the mage lab gateway, your token and model usage are aggregated anonymously, but no user or message data is stored on our servers. However, if you send requests to third parties, privacy risks are yours to manage. Our full data privacy policy can be found [here](https://magelab.ai/privacy).

## ADVANCED USERS

For those who are already familiar with the basic chat and core functionality in mage lab and are looking to enhance their experience and customize the capabilities of the platform, here you'll find details about configuring settings, selecting voice and language models, managing context length, and utilizing various tools. Let's dive into the configuration options and tools available to elevate your experience!

### settings panel

There are five subpanels in settings: quick settings, api settings, path settings, tool scope, and visual effects. 
If you are logged into the mage lab gateway there will be a sixth with balance information.
#### general settings

##### llm models

- Select your preferred language model for chatting. Available models vary depending on what provider has been selected. We recommend using tool-capable models like gpt-5 and qwen3 to get the best experience with mage lab.
- You can switch between models at any time during a conversation. If you’re not happy with the answers you’re getting, or just want a second opinion, switching is built right into the flow. 
- Keep in mind that how well local models will perform depends on your computer's specifications.
- If you choose a third-party AI Provider, such as OpenAI, you'll need to have a funded account and an API key.
- mage lab also offers a gateway service allowing direct access to a curated collection of top models under one pay as you go user managed account.

##### voice models

You can choose from different voice models for your text-to-speech interactions. The availability of voice models depends on your AI provider.

##### chat history
Select from the chats available in your history or start a new one.

##### context window

- For inference providers like OpenAI, context length typically isn't a significant issue. However, remember that more tokens (word segments)  both in and out the more it will increase costs.
- Context length can have a big impact on local LLM performance - even for frontier models. This is especially true with locally hosted models, depending on your computer's specification. This also includes having too much context in the system prompt, not just in the overall chat history.
- To help manage this, mage lab allows you to shorten the chat history by setting the number of messages you want to send pre request, as well as allowing access to edit your system prompt and adjust your active tool set. This flexibility lets you tailor performance and behavior to best fit your budget and needs.

##### tool debugging
Toggle on additional messages showing the model <--> tool exchanges.

##### yolo mode
Bypasses the user confirmation for executing local code. Warning: this is an advanced user feature and should not be enabled without carefully understanding the implications. This software comes as is and we are not liable for damage you cause to your own system.

##### count tokens
Adds a token usage counter in the top right corner of the canvas to help monitor and manage llm context length (Format: SystemPrompt/User&AssistantExchange/Total).

##### random toast
Adds a random default greeting when starting a new conversation. Toggleable in the General Settings subpanel.

##### contemporaneous awareness
Inform the AI model about the current time and the folder it’s working in. You can turn this on or off in General Settings

#### api settings
Here you can choose and configure model providers. To see what models are available you can look in the LLM, TTS, and Transcription provider dropdown menus. Options will change over time. You can also configure new providers using the Provider Management interface at the bottom of the subpanel.

#### path settings
Configure the default paths for mage to look for music and movies; set your workspace and chat history folders; and access and adjust your system message and environment file. NOTE: The Play Audio and Play Video tools use their respective paths when searching for requested content. 

#### tool scope
Access the tools available on your system. By default, you will start with the mage core system tools. Over time you can add to those via adding community tools, or creating them yourself!

##### tools concepts

- Tools are essential to the mage lab interface. Without them, it is just a simple chat interface. All the advanced features of mage lab rely on these tools. While many language models support tool usage, not all do. Internally, we primarily test using gpt-5 models, and/or the qwen3 series of open source models, but have verified functionality for all models offered through our gateway.
- mage lab includes a basic set of tools that let you open various types of files and media. These tools may or may not provide visual feedback when using them. When you ask mage to write a file, the file is already written by the time you see the tab open. The tab is incidental, and there to provide a visual queue and additional interactivity for your collaboration.
- Tools can potentially run in the background without interacting with the interface. However, you can still see the tool calls and tool responses by **toggling on tool debugging** in the settings general settings subpanel. This also allows you to evaluate the AI responses to see if it is responding honestly, or hallucinating, and what tools and responses are happening as part of each message request.
- The mage core system tools run locally on your machine.

mage lab is highly customizable, providing endless possibilities for integration and expansion. You can create or import your new tools and the possibilities are endless. 

##### tool toggles

The tools available in mage lab can be configured in the settings panel. Only the tools that are toggled on will be "visible" to mage. If a tool isn’t toggled on, mage is not aware of it, as it is not included in the scope of your current session.

The mage core system tools that come installed

     calculate
     open workspace
     open links
     open mage docs
     play audio
     play video
     read file
     read website *
     run python
     search files
     search folders 
     search images **
     search web **
     write file
     run bash (Mac and Linux) or run powershell (Windows) Nore: default off
     
     * simple BeautifulSoup tool, has limited capabilities
     ** requires mage lab gateway, or community tool configuration

You can find more community tools, and contribute, on our Github [here](https://github.com/Sapient-Artifice/mage-lab-community-tools).

To use a community tool, simply download it, and drop it into your ~/Mage/Tools directory.

#### visual effects
Some basic ways to customize your canvas.

#### balance
If you are using the mage lab gateway a sixth subpanel will appear where you will be able to monitor your balance, as well as adding additional credit to your account. Additional account tools and settings are available through the web interface found at magelab.ai.

## POWER USERS
Here, you'll find information on AI providers, model locations, self-hosted options, and custom tools that will empower you to enhance your workflows and maximize the capabilities of mage lab.

### customization

#### ai providers
In mage lab, you can easily select which AI provider fits your needs, whether you’re using cloud services or locally hosted. The available models are linked to the provider, so changing the provider updates what models are available.

Inference providers (e.g. OpenAI, Grok, Anthropic, etc.) provide not only language model responses, but also transcription, text-to-speech, and additional services. To use a provider, you need the resource's URL (e.g., https://api.openai.com/v1 or localhost:11434/v1) and an API key (when required).

Sapient Artifice can also be your provider if you choose. The gateway brings together a curated list of the top models from both the closed and open source communities into a single user account. When initially signing up for your account the gateway will be populated will a bit of credit and access to a few of those models to let you try things out. If you choose to add additional funds to your account, the full suite of supported models will become available. Your costs will be 1.2x the current API costs for the selected model.

##### gateway models

    Anthropic/claude-3-5-haiku	
    Anthropic/claude-opus-4-1
    Anthropic/claude-sonnet-4-5
    Brave/web-search
    Cerebras/qwen-3-235b-a22b-instruct-2507
    Cerebras/qwen-3-32b
    Cerebras/zai-glm-4.6
    Cerebras/gpt-oss-120b
    Google/gemini-2.5-flash	
    Google/gemini-2.5-flash-lite-preview	
    Google/gemini-2.5-pro
    OpenAI/gpt-5-2025-08-07
    OpenAI/gpt-5-mini
    OpenAI/gpt-5.1
    OpenAI/gpt-5.1-chat-latest
    OpenAI/gpt-5-nano
    OpenAI/o4-mini
    OpenAI/whisper-1
    OpenAI/gpt-4o-mini-transcribe
    OpenAI/gpt-4o-mini-tts
    OpenAI/tts-1
    xAI/grok-3-mini
    xAI/grok-4-0709
    xAI/grok-4-fast-non-reasoning
    xAI/grok-code-fast-1

Note: We cannot control when Providers change their model selections, but will stay up to date and keep you informed when there are changes. Pricing information can be found [here](https://magelab.ai/pricing).

Additionally you can manually configure 
- Ollama (locally hosted - open-source models)
- Any OpenAI compatible API 
- Note, cross-model integrated chat (ie using multiple models in the same conversation) for untested providers/models may expose bugs. If you see this in the wild, please let us know.

##### model types

You can select a separate provider (if desired) for each of the following AI resources in the settings panel

- LLM Inference
- Text to Speech
- Transcription
- Vision (coming soon)
- Image Generation (coming soon)

You can easily add new custom providers in addition to commons providers included in the settings.  If you want to tie in totally custom models for something less common like SLAM, or some other specific data models, these can also be integrated similarly together with the use of tools.

##### ai inference costs

While each AI provider (OpenAI, Grok, etc) offers their own interface for using their models, they also provide API keys to provide AI inference (at a cost). mage lab is compatible with all "OpenAI standard" APIs which covers most providers. Open source models like qwen3 and cheaper proprietary models like gpt-5-mini offer economical yet impressive performance. For more advanced use cases using frontier level models like gpt-5 and Qwen 480B can deliver stunning results. 

Please note that these commercial models require an API key and usually charge by the token. mage lab serves as your user-friendly interface to interact with these various models, allowing you to easily find the perfect fit for your projects! To read more about API keys please refer to the AI provider section.

### self hosted (local ai)

  Docker: Docker containers are available for TTS and transcription, as well as Ollama
  
  Ollama: Ideal for running LLMs locally within your system capabilities
  
  Recommended Models: mage lab suggests qwen3 when using locally hosted LLMs
  
  Compatibility: We use the OpenAI standard libraries for responses, transcription, and text-to-speech. Local AI should be OpenAI compatible for use with mage lab (like Ollama)

### custom tools

Out of the box, mage lab provides a set of core tools and functionality that will allow you to start working right away - and for a lot of standard workflows that will already be enough to get the job done. 

However, what makes mage truly powerful is the ability to customize the system flexibly. The next sections walk you through the two most important methods currently available to unlock that potential.

**The first is Custom Tools.** Tools allow you to extend the capabilities of your LLMs using custom Python code. Once configured, the tools you write are accessible directly from the LLM as extended core functionality. 

**The second is Ask Assistant.** Ask Assistant is a simple HTTP API that provides API access to the LLM programmatically. This allows the capacity for mage lab to be a part of automation loops, and integrated into other applications. 

We will now walk through 

**How to create and register your own custom tools** (ie functions the model can call).

**How to call the `ask_assistant` API** from your code to integrate mage lab into your automation and workflows.


#### custom tools and automation
A “tool” is a plain Python function that:
 
- Is decorated with `@function_schema(...)` so mage lab can advertise its name/params to the model.
-  Lives in a discoverable location, either inside the repo (core tools) or in your per-user Tools folder (custom tools).
-  Returns a concise, user-facing string (or structured content if you handle it yourself) describing the result.


#### function schema
Use the `@function_schema` decorator to describe your tool for the LLM. It enforces presence of required params and serializes all params as strings for the model to call.

Minimal contract:
```python
from utils.functions_metadata import function_schema

@function_schema(
    name="your_tool_name",
    description="What this tool does, concisely.",
    required_params=["param1", "param2"],
    optional_params=["maybe_param"]  # optional
)
def your_tool_name(param1: str, param2: str, maybe_param: str = "") -> str:
    """
    :param param1: Brief description (shown in help UIs)
    :param param2: Brief description
    :param maybe_param: Optional parameter description
    """
    # Do work and return a short, user-friendly message
    return "Done!"
```
Notes:
 All parameters are treated as strings at the schema layer. Parse/convert internally as needed.
 Docstring `:param name:` lines are parsed and can show up in help UIs.
 The decorated function gains a `schema` attribute that Mage uses to advertise tools to the model.

#### mage utilities
As time passes we will open up and documented these utilities. Sorry, to those working without source atm. The examples will provide some of that functionality for now, and we will continue to expand both functionality and it's documentation...promise! 

- `config` from `backend/config.py`: runtime settings and paths (e.g., `config.workspace_path`, `config.tools_folder`).
- `ws_manager` from `backend/ws_manager.py`:
    - `open_tab(path: str)`: ask the frontend to open a file in a new tab.
    - `open_url(url: str)`: ask the frontend to open a browser tab.
    - `send_tool_debug_message(message_type, content, tool_name=None, args=None)`: surface debug info in supported UIs.
    - `request_user_confirmation(script, function_name, arguments)` (async): prompt the user for confirmation; returns bool.
- Logging: use Python `logging` for backend logs; everything is written to `~/.config/magelab/magelab.log`.

Example usage inside a tool:
```python
import logging
from config import config
from ws_manager import open_tab, send_tool_debug_message

logger = logging.getLogger(__name__)

# ... inside your tool
send_tool_debug_message("tool_message", "Starting work...", tool_name="your_tool")
logger.info("Workspace is %s", config.workspace_path)
# Optionally open a result file in the editor tab
open_tab("/absolute/or/expanded/path/to/result.txt")
```

#### tool placement
Mage loads tools from multiple places at startup

- Built-in: `backend/functions/core`
- User Tools folder: `config.tools_folder` (defaults to `~/Mage/Tools`). All `*.py` files are recursively imported; any callable with a `.schema` attribute is registered as a tool and categorized as `community`.

Recommendations

- For personal or team extensions, the per-user Tools folder allows you to update without touching source code directly.
- Name collisions: function names must be unique across all loaded tools.
- Imports: the loader temporarily adds each tool file’s directory to `sys.path`, so you can import sibling modules in the same folder.
- Reloading: the registry loads at server startup. After adding or changing tools, restart the backend to pick them up.

#### errors & logs

- File log: `~/.config/magelab/magelab.log` (rotating). Tail it while developing:
    - macOS/Linux: `tail -f ~/.config/magelab/magelab.log`
    - Windows: open the file in your editor or use PowerShell `Get-Content -Wait`.
- HTTP: `GET http://127.0.0.1:11115/logs?lines=200` returns recent log lines.
- Common errors:
    - Import errors while loading your tool module.
    - Schema errors if required/optional params do not match the function signature.
    - Exceptions during tool execution (caught and logged with function name).

#### faqs
- Parameter types: all tool parameters are surfaced as strings; cast inside the function.
- Return shape: tools typically return a short string; if you need rich output, write files and return a summary plus a link/path, or use `open_tab`.
- Hot reload: not supported; restart the backend after adding/updating tools.
- Security: tools execute with the backend’s permissions. Validate inputs and use safe paths (prefer `config.workspace_path`). 
- My tool doesn’t appear: ensure you used `@function_schema`, resolved any import errors, and restarted the backend.
- Can I ask for confirmation? Yes—use `request_user_confirmation` (async). You’ll need to run it within an async context or schedule it appropriately.
- Show tool debug: use `send_tool_debug_message` for development; some UIs surface these messages.

#### “hello world”
Place this in your Tools folder (e.g., `~/Mage/Tools/hello_world.py`) and restart the backend.

```python
# ~/Mage/Tools/hello_world.py
import logging
from utils.functions_metadata import function_schema
from ws_manager import send_tool_debug_message

logger = logging.getLogger(__name__)

@function_schema(
    name="hello_world",
    description="Return a friendly greeting.",
    required_params=["name"],
    optional_params=["punctuation"]
)
def hello_world(name: str, punctuation: str = "!") -> str:
    """
    :param name: Who to greet
    :param punctuation: Optional trailing punctuation
    """
    try:
        send_tool_debug_message("tool_message", f"Greeting {name}", tool_name="hello_world", args={"name": name})
        greeting = f"Hello, {name}{punctuation}"
        logger.info("hello_world produced: %s", greeting)
        return greeting
    except Exception as e:
        logger.error("hello_world failed: %s", e)
        return f"Error: {e}"
```
How to use it

- Ask the assistant to call `hello_world` by name, or describe the action (“Greet Sam using the hello_world tool”).
- The model can select the tool and supply params; the result returns to the chat UI.


### ask assistant
You can inject messages directly into Mage’s conversation loop via an HTTP endpoint. This is useful for headless automation, scripts, or connecting other apps to mage lab.

Endpoint

- `POST http://127.0.0.1:11115/ask_assistant`
- JSON body: `{ "message": "Your text input" }`
- Success response: `{ "status": "success", "message": "Message added to transcription queue" }`

What happens

- The backend enqueues your text on `transcription_queue`.
- The chat processor reads messages, builds LLM requests with tool schemas, handles tool calls, and streams assistant responses to the frontend WebSocket and to TTS if enabled.
- Logs for the request are written to `~/.config/magelab/magelab.log` and can be fetched via `/logs`.

#### send request
```python
# send_message.py
import requests

BASE_URL = "http://127.0.0.1:11115"

resp = requests.post(f"{BASE_URL}/ask_assistant", json={"message": "Summarize the current project status."})
resp.raise_for_status()
print("enqueued:", resp.json())

# (optional) fetch recent logs
logs = requests.get(f"{BASE_URL}/logs", params={"lines": 100}).json()
print("last logs:")
for line in logs.get("lines", []):
    print(line)
```
With the mage lab app running, from a terminal run `python send_message.py`. Watch the app UI (or logs) for the assistant’s response.

#### get response 
You can also stream responses via the WebSocket if you want programmatic access to the assistant’s textual responses. To do this you connect to the WebSocket and listen for messages of type `assistant`:
```python
# stream_responses.py
import asyncio
import json
import websockets
import requests

BASE_URL = "http://127.0.0.1:11115"
WS_URL = "ws://127.0.0.1:11115/ws"

async def main():
    async with websockets.connect(WS_URL) as ws:
        # Kick off a request via HTTP
        r = requests.post(f"{BASE_URL}/ask_assistant", json={"message": "Say hello and call any greeting tools if helpful."})
        r.raise_for_status()
        print("enqueued:", r.json())

        # Read a few messages
        for _ in range(50):
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "assistant":
                print("assistant:", data.get("text"))
            elif data.get("type") == "tts_audio":
                print("(tts audio chunk received)")
            elif data.get("type") == "tool_debug":
                print("tool_debug:", data)

asyncio.run(main())
```
Notes:

- The WebSocket emits a variety of message types (`assistant`, `tts_audio`, `tool_debug`, `ping`, etc.). Filter for what you need.

- This is read-only; to send more text programmatically, use `POST /ask_assistant` again.

#### parsing mage ws messages 

Here’s a protocol guide for parsing Mage messages over WebSocket.

    **Endpoints**
         - `BASE_URL`: http://127.0.0.1:11115
         - `WS_URL`: ws://127.0.0.1:11115/ws

    **Connection**
         - Connect to `WS_URL` and accept JSON messages.
         - Server sends a heartbeat: `{"type":"ping","ts": <float>}` every ~30s. Ignore for parsing; use for liveness.

    **Server → Client: Message Types**
      `assistant`: final assistant text for the current phase.
         - Fields: `text: string`
         - Notes: May arrive multiple times within one user turn (e.g., pre-tools, post-tools). Not token-by-token; already concatenated and “<think>” removed.
      `assistant_complete`: signals the assistant+tools cycle finished for the last user input.
         - Fields: none
      `token_count`: token usage (only if enabled in config).
         - Fields: `sys_count: int`, `win_count: int`, `total_count: int`
      `tts_audio`: audio chunk for text-to-speech.
         - Fields: `audio_data: base64-string` (base64 of audio file bytes)
         - Notes: Sent only when audio sending isn’t paused. Each message is a complete file payload; play immediately and discard.
      `transcription`: transcription of audio you sent.
         - Fields: `text: string`
         - `tool_debug`: debug stream for UI/logging.
       Fields: `message_type: "user_message" | "mage_message" | "tool_message" | "function_call" | "warning_message"`, `content: string`, optional `tool_name: string`, optional `args: object`
         - Notes: Informational; not required to render core chat.
      `open_file`: request to open a file in the client.
         - Fields: `filepath: string`
      `open_url`: request to open an external URL.
         - Fields: `url: string`
      `notify`: surface an OS-style notification.
         - Fields: `title: string`, `body: string`
      `ping`: heartbeat.
         - Fields: `ts: float`

    **Client → Server: Message Types**
      `audio`: send recorded audio for transcription.
         - Fields: `data: "data:audio/<mime>;base64,<payload>"`
         - Response: server echoes `transcription` and enqueues it for assistant processing.
      `text`: send a typed message.
         - Fields: `text: string`
      `control`: control audio behavior.
         - Fields: `action: "mute" | "unmute" | "start_recording" | "stop_recording"`
         - Notes: While muted or recording, TTS files are discarded server-side.
      `confirmation_response`: answer a confirmation request.
         - Fields: `confirmation_id: string`, `confirmed: boolean`
         - Notes: Complements a server `confirmation_request` (which arrives via `tool_debug` UI and also as a dedicated `confirmation_request` message if used).

      **Flow Expectations**
      You send `text` or `audio`.
      You receive zero or more `token_count` (if enabled).
      You receive one or more `assistant` messages (pre/post internal phases).
      You receive `assistant_complete`.
      With tools:
      You may see an initial `assistant` (tool planning), tool debug in `tool_debug`, then final `assistant`, then `assistant_complete`.
      Voice:
      TTS audio files arrive as `tts_audio` (base64). Handle immediately; they represent complete playable chunks.
      Audio sending can be paused by server; missing `tts_audio` during mute/recording is expected.

      **Parsing Recommendations**  
      Switch on `type` for routing; treat unknown types as no-ops.
      Accumulate `assistant` texts per user turn until `assistant_complete`.
      Ignore or log `tool_debug` for developer visibility only.
      Treat `ping` as liveness; reconnect if heartbeats stop.
      For `tts_audio`, base64-decode and play; do not persist unless needed.
      For `token_count`, display or log as optional metadata.

**Minimal Client Pseudocode**

       On message:  
       if `type == "assistant"`: buffer or render `text`
       if `type == "assistant_complete"`: finalize the turn
       if `type == "tts_audio"`: play base64 `audio_data`\
       if `type == "token_count"`: show usage
       if `type == "transcription"`: display transcription
       if `type == "open_file"|"open_url"|"notify"`: perform action as appropriate
       if `type == "tool_debug"`: log for dev tools
       if `type == "ping"`: mark alive

#### troubleshooting

  - Ensure the backend is running on `127.0.0.1:11115` (or change `API_HOST`/`API_PORT`).
  - Empty messages are rejected with HTTP 400.
  - Check `~/.config/magelab/magelab.log` or `GET /logs` if something fails.
  - Tools available to the model are determined at startup (schema list comes from `FunctionsRegistry`). Restart the server after adding tools.
 
## DEVELOPERS

If you want to make more serious integrations or changes to the platform, the source code is not currently open to the public, but reach out and we will find a way to support and collaborate with you!
