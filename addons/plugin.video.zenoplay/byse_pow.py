"""Portable implementation of the player's automatic computation check."""
import time
MASK=0xffffffff

def qr(a,b,c,d):
    a=(a+b)&MASK;d^=a;d=((d<<16)|(d>>16))&MASK
    c=(c+d)&MASK;b^=c;b=((b<<12)|(b>>20))&MASK
    a=(a+b)&MASK;d^=a;d=((d<<8)|(d>>24))&MASK
    c=(c+d)&MASK;b^=c;b=((b<<7)|(b>>25))&MASK
    return a,b,c,d


def seed(text):
    a,b,c,d=1779033703,3144134277,1013904242,2773480762
    for byte in text.encode('latin1'):
        a=(a+byte)&MASK;a=((a<<7)|(a>>25))&MASK;a,b,c,d=qr(a,b,c,d)
    return a,b,c,d


def first_word(prefix,solution):
    a,b,c,d=prefix
    for byte in str(solution).encode('ascii'):
        a=(a+byte)&MASK;a=((a<<7)|(a>>25))&MASK;a,b,c,d=qr(a,b,c,d)
    for _ in range(8):a,b,c,d=qr(a,b,c,d)
    memory=[0]*512
    for i in range(512):
        a,b,c,d=qr(a,b,c,d);memory[i]=a^c
    for _ in range(2):
        for i in range(512):
            value=(memory[i]+memory[memory[i]&511])&MASK
            value=((value<<13)|(value>>19))&MASK
            value^=(memory[(i+1)&511]*2654435761)&MASK
            memory[i]=value;a^=value;a,b,c,d=qr(a,b,c,d)
    a,b,c,d=qr(a,b,c,d);result=a
    for value in memory[:64]:
        result=(result+value)&MASK;result=((result<<5)|(result>>27))&MASK;result^=(value*2246822519)&MASK
    return result^c


def solve(nonce,difficulty,progress=None,timeout=150):
    if not isinstance(difficulty,int) or not 0<=difficulty<=20:raise ValueError('Неподдържана сложност на проверката на Byse.')
    if not difficulty:return '0'
    prefix=seed(nonce+':');limit=1<<(32-difficulty);start=time.monotonic();number=0
    while time.monotonic()-start<timeout:
        if number%32==0 and progress and progress(min(85,35+int(50*(time.monotonic()-start)/timeout))):raise ValueError('Зареждането е отказано.')
        if first_word(prefix,number)<limit:return str(number)
        number+=1
    raise ValueError('Проверката на Byse отне прекалено дълго. Опитайте отново или изберете друг източник.')
