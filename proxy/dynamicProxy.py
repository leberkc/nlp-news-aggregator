import json
import urllib2
from selenium import webdriver
from socket import error as SocketError
import socket
# from pyvirtualdisplay import Display



#site = 'http://www.google.com'
site = 'http://www.bing.com'

def is_bad_proxy(pip):
    
    try:
        proxy_handler = urllib2.ProxyHandler({'http': pip})
        opener = urllib2.build_opener(proxy_handler)
#        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        opener.addheaders = [('User-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36')]
        urllib2.install_opener(opener)
        req = urllib2.Request(site)  # change the URL to test here
        sock = urllib2.urlopen(req)
        print sock.geturl()
        print sock.getcode()
        #print "Server:", sock.info()
        
    except urllib2.HTTPError, e:
        print 'Error code: ', e.code
        return e.code
    except Exception, detail:
        print "ERROR:", detail
        return True
    return False

def proxy_extractor():
    
    # display = Display(visible=0, size=(800, 600))
    # display.start()
    # driver = webdriver.Firefox() # Or Firefox()
    
    driver = webdriver.PhantomJS('/usr/local/bin/phantomjs') #Changed this part of code
    
    print('Opening browser in background...')
#    driver.get('https://www.proxynova.com/proxy-server-list/elite-proxies/')
    driver.get('https://www.proxynova.com/proxy-server-list/country-cn/')

    data = []
    print('Extracting proxy table...')
    for tr in driver.find_elements_by_xpath('//table[@id="tbl_proxy_list"]//tr'):
        tds = tr.find_elements_by_tag_name('td')
        if tds:
            data.append([td.text for td in tds])
    
    print('Closing browser...')
    driver.close()
    
    print('Extracting proxies...')    
    
    proxy_list = []
    for i in xrange(12):
        proxy_list.append(str(data[i][0] + ':' + data[i][1]))
            
    for i in xrange(13, len(data), 1):
        proxy_list.append(str(data[i][0] + ':' + data[i][1]))
    
    return proxy_list

def main(mylist):

    socket.setdefaulttimeout(30)
    
    goodProx = []    
    
    for currentProxy in mylist:
        print('Reading and analyzing proxy...')
        if is_bad_proxy(currentProxy):
            print "Bad Proxy %s" % (currentProxy)

        else:
            print "%s is working" % (currentProxy)
            goodProx.append(currentProxy)
            
    with open('good-proxies.txt', 'a') as myfile:
        for item in goodProx:
            myfile.write("%s\n" % item)

main(proxy_extractor())










