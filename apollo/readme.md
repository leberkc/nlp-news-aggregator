Provide brief description of the application...

Can you provide details on what each of the files do as well as describe how to start
and stop the application?

Also, I remember you mentioned you had designed the backend so Matt would be able to
toggle on and off certain features/feeds, etc....

Can you provide details on what and where this can be done?


`alexachron.py`
-------------
Scripts ending with "chron" are simply the routines set to be periodically called. They invoke the work
of other classes. In this case, there is no "alexa" class corresponding to "alexachron" because the
collection of alexa page ranks is too straightforward to merit the creation of its own Python class.

Alexa rankings are a measurement of website popularity: https://en.wikipedia.org/wiki/Alexa_Internet
The "alexchron" script queries every unique source in our database and gets its Alexa rank. "Unique source" should be
understood as the website "stem." For example, we may have collected several articles from the BBC. The URL
of one might be bbc.co/finance/widget-sales-soar and another might be bbc.co/arts/widget-movie-break-box-office-records.
These two articles would produce only one unique source, "bbc.co", has its rank retrieved.

These ranks are saved back to their own table. The idea is that we take a reading every month, week, or whatever, and
find out how popular each source is. The more popular a source is, the more influence it likely has.

`apollo.py`
---------
This is the class that models our hypothetical COLLECTIVE ACTION POTENTIAL.
As other experiments should do, the Apollo class makes primary use of
CorpusBuilder and CorpusAnalyst to collect documents and perform the
rudimentary processing.

`apollochron.py`
--------------
Scripts ending with "chron" are simply the routines set to be periodically called. This one invokes the
work of the Apollo class. The script simply builds an instance of Apollo and tells it to do its thing.

`bagchron.py`
-----------
This is the script to be called by the system Crontab. Invoke the Bagger class to periodically bag words.
Unlike our collection routines, which we can think of as mouths, this routine is more like a stomach that
runs on a clock. At every time interval, tell the stomach to digest some more of the food inside it.

The idea of separating collection and processing routines was so that the system would have several smaller jobs
instead of few large jobs. This is defensive design. We want to avoid the system choking while trying to scrape
a lot of material, parse it, segment it, clean it up, and store it all in a single effort. Smaller routines are
easier to debug and typically avoid tripping over each other.

Word-bagging is probably called most frequently. There may or may not be still-undigested food in the system's
stomach, but it does no harm to call this routine when everything has already been bagged.

The bag-of-words format is convenient for analysis and typically the format of choice for natural language processing.
However, our experience has shown us that it can become time-consuming in some languages. Chinese, for example, must
first be segmented, and this takes time. Word-bagging and/or segmenting cannot be so disruptive to collection (eating).

`bagger.py`
---------
This is the class invoked by the word-bagging script above. This class queries the database for a given number of
yet-unbagged rows, performs word-bagging on them, and then saves the bag-of-words back to its row. Note that this
is a non-destructive process! We should always have the original content in the row, too, in case we ever want to
go back to it.

Recall that each collected article or social media post becomes a row in our database. When collected,
content is stored as-is: typically including stop-words, punctuation, line-breaks, or other tokens we probably won't want
when actually studying the content. A row is "unbagged" if its bag_of_words field is NULL.

Bagger will find the oldest n unbagged rows and run the necessary processes on them. If the row is marked as English, then
the word-bagger will bag according to English. If the row is marked as Chinese, then the word-bagger will first segment the
text, and then bag.

Bagged text is stored in the bag_of_words cell as a TAB-separated list of tokens. Note that this was originally a comma-
separated list of tokens, but this led to problems: what if we want to use punctuation as a feature? Also understanding an
entry like, "this,,,and,that," becomes ambiguous. Thus, the decision was made to separate with TABs.

`corpusanalyst.py`
----------------

`corpusbuilder.py`
----------------
This is a fetcher/collector tool. It differs from our other "collectors" in that it collects things already stored in our
database, whereas something like rss or Weibo collect from the web.

Think of this class as a librarian or a clerk in a store. It receives requests like, "Fetch me everything in English from
May to December, 2017, and everything in Chinese from Weibo from April to May, 2017.

Under the hood this class's points of reference are database table names and row key-primeros (KPs). Requests like the one
above are translated into a list of name-row pairs. A final fetch() command then tells the virtual clerk to take the list
generated, walk into the back room (database) and actually bring back an armfull of rows.

`freeweibo.py`
------------
This class sends an HTTP request to FreeWeibo and stores what it finds.

Like RSS and Weibo, this is a collection class, customized for a specific information package. This class works because
developers examined the HTML page layout and Document Object Model (DOM) of FreeWeibo and found out which selector queries
will target the content we want.

If the webmasters of FreeWeibo drastically change their page layout or presentation, then this Python class will need to be
redesigned accordingly!

Once content is scraped from FreeWeibo, it is saved (un-bagged) to the database to be bagged later.

`freeweibochron.py`
-----------------
This is the CronJob script for collecting content from FreeWeibo. We've found that content turnover on FreeWeibo is pretty high,
so it would be worth running this script frequently.

`keyworder.py`
------------
This was incomplete at the time of writing. The idea was to create a class to assist with keyword search.

`rss.py`
------
This class sends HTTP requests to various RSS-formatted news sources and stores what it finds.

Like other collection classes, RSS depends on adherence to a specific format. RSS is a widely-known, though poorly enforced spec.
"Poorly enforced" means that no distortion of the content will really prevent a document from being an RSS feed. Compare this to an
image file: whatever the format, an image is supposed to indicate its width, its height, and then provide an array of pixel values
indicating which color should appear where. If any of these parts are missing, we are at a loss for how to display the entire image.
An RSS is supposed to contain XML fields like "content", "title", "keywords", "summary", and "language," though not all do.

Inevitably, certain assumptions must be made about the content we find claiming to be formatted as an RSS feed. Much of the code in
this Python class tests for presences and absences of the expected fields. We try to make an educated guess and save as much text as
possible.

Unlike the FreeWeibo collector class which always knows where to go to get its content, RSS must first read from a bank of RSS news
feeds in our database. This means that RSS typically talks to the database twice. The first time it asks, "Which news feeds should
I go get?" The second time, it inserts into the database one row for each article it found. The bank of RSS feeds in our database
also provides a convenient way to add new sources, remove ones we no longer want to collect, and even disable or "silence" a feed
without removing it.

`rsschron.py`
-----------
This is the script which tells the RSS class to perform its task. Remember that not all Python classes do the same things:
some are just definitions of objects; others (like this or any other "chron" script) are instructions to be performed.

`weibo.py`
--------
This class sends HTTP requests to Weibo and stores what it finds in our database, making it another content-collection class.
As of this writing, the Weibo class was still under development. This is owed to the complexity of the Weibo interface. Collecting
from FreeWeibo and RSS were straightforward because contents was readily displayed on the pages immediately reached. Weibo is more
defensive. Users must first log in with an approved account. Code for locating the input fields and injecting a username and password
has been implemented.

Next, users who have successfully logged in are shown an initial array of posts. However, most of these are advertisements and not of
much use for detecting reactions to a particular topic. To find posts related to events other than 20% off shoes, Weibo makes it
necessary to search for a topic. Searching for a topic is not much different than logging in: the code must locate the input field and
inject a string.

Like FreeWeibo, knowing where page components are located in the DOM tree was determined by hand. Developers must actually log in and
examine the HTML and CSS. Likewise, if Weibo changes their page structure or layout, this work may need to be redone.

As of this writing, discussions were still ongoing about which parts of the page would be worth tracking. For instance, Weibo awards
ranks for members' contributions and distinguishes between "officially registered" and "amateur" accounts. Nominally, this is to
prevent users from creating accounts claiming to represent other people or companies. In the context of censorship detection, it may
be informative to take note of which accounts have been granted any kind of approval by the site's administration. These distinctions
are seen on Weibo posts as small graphic badges with different colors and meanings. Work left off trying to make an exhaustive list of
all these badges so that values for a corresponding database column could be determined.

It may also be informative to track which topic searches returned which Weibo posts.

Finally, developers also anticipated that bias may be introduced because of the forced log-in. An account created for automated
collection of posts on controversial topics could appear to the Weibo system as a person interested in controversial things. We
should consider that the system might flag our account or at the very least adjust its algorithms to return more molifying content
to a potential troublemaker.
