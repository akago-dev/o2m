from __future__ import print_function
from time import sleep

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.System import readers
from smartcard.scard import SCardEstablishContext, SCardTransmit, SCardConnect, SCARD_PROTOCOL_T1, SCARD_PROTOCOL_T0, SCARD_SHARE_SHARED, SCARD_S_SUCCESS, SCARD_SCOPE_USER
from smartcard.Exceptions import NoCardException

from events import Events
import pprint

cmdMap = {
	"mute":[0xFF, 0x00, 0x52, 0x00, 0x00],
	"unmute":[0xFF, 0x00, 0x52, 0xFF, 0x00],
	"getuid":[0xFF, 0xCA, 0x00, 0x00, 0x00],
	"firmver":[0xFF, 0x00, 0x48, 0x00, 0x00],
}

class PrintObserver(CardObserver):
    """A simple card observer that is notified
    when cards are inserted/removed from the system and
    prints the list of cards
    """
    def __init__(self):
        self.events = Events()
        self.muted_readers_names = []
        self.active_cards = {}

    def update(self, observable, actions):
        # self.mute_all_readers()
        (addedcards, removedcards) = actions
        for card in addedcards:
            self.mute_reader(card.reader) # The reader has a card on it so we can try to remove the beep
            # Methode 1
            int_id = self.get_id(card.reader)
            card.id = self.convert_to_hex_as_string(int_id)
            # print("METHODE 1 : +Inserted: {} in reader : {}".format(card.id, card.reader))

            # Methode 2
            readerObject = self.get_reader_by_name(card.reader)
            uid_str = self.get_id_with_reader(readerObject)
            if uid_str != None:
                print('METHODE 2 : Card id : {} in reader : {}'.format(uid_str, readerObject))
            else:
                print('METHODE 2 : ERROR')

            # active cards dict update
            self.active_cards[card.reader] = card

        for card in removedcards:
            # print("-Removed: {} from reader : {}".format(card, card.reader))
            card.id = self.active_cards[card.reader].id
            print('id removed : {}'.format(card.id))
            self.active_cards[card.reader] = None

        self.events.on_change(addedcards, removedcards, self.active_cards) # Launch the event 

    '''
        Mute the readers | Remove the beep sound on card/tag connection
        Works only if a card is on the reader
        Throw an exception otherwise

        Two differents methods that works the same way but throw differents exceptions

        Once a reader is muted, the settings is live until the reader is unplugged.
        we store in a the muted_readers_names list of the readers already muted and launch the mute command only if useful
    '''
    def mute_reader(self, reader_name):
        reader = self.get_reader_by_name(reader_name)
        if reader != None:
            if reader.name not in self.muted_readers_names:
                # Methode 1
                # try:
                #     self.launch_command(reader.name, cmdMap['mute'])
                #     print('Reader {} muted!'.format(reader.name))
                #     self.muted_readers_names.append(reader.name)
                # except SystemError as err:
                #     print(err)
                #Methode 2
                try:
                    connection = reader.createConnection()
                    connection.connect()
                    connection.transmit(cmdMap['mute'])
                    print('Reader {} muted!'.format(reader.name))
                    self.muted_readers_names.append(reader.name)
                except NoCardException as err:
                    print('Error : {} on reader : {}'.format(err, reader.name))

    '''
        Première méthode de connexion à la carte
        Le nom du reader suffit mais renvoie plus de donnée que nécessaire (obligé de tronquer le résultat)
    '''    
    def get_id(self, reader_name):
        return self.launch_command(reader_name, cmdMap['getuid'])

    def launch_command(self, reader_name, command):
        try:
            hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
            assert hresult==SCARD_S_SUCCESS

            hresult, hcard, dwActiveProtocol = SCardConnect(
                hcontext,
                reader_name,
                SCARD_SHARE_SHARED,
                SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)

            # hresult, response = SCardTransmit(hcard,dwActiveProtocol,[0xFF,0xCA,0x00,0x00,0x00])
            hresult, response = SCardTransmit(hcard,dwActiveProtocol, command)
            
            return response[:len(response)-2]
        except SystemError as err:
            print("Error in launch command : {}".format(err))
            return None

    ''' 
    Deuxième méthode de connexion 

    Avantages : Plus simple à lire, pas besoin de retirer les données en surplus
    Necessite l'object PCSCReader et pas juste le nom du reader (chaine de caractère)
    '''
    def get_reader_by_name(self, reader_name):
        return next((x for x in readers() if x.name == reader_name), None)

    def get_id_with_reader(self, reader):
        return self.launch_command_with_reader(reader, cmdMap['getuid'])

    def launch_command_with_reader(self, reader, command):
        try:
            connection = reader.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit(command)
            return self.convert_to_hex_as_string(data)
        except NoCardException as err: 
            print(err)
            return None

    '''
        Util function used by both methods
    '''
    def convert_to_hex_as_string(self, data):
        hexData = [format(i, 'X').zfill(2) for i in data] # we convert to hex with format and add a 0 digit if necessary
        return ''.join(hexData)

class NfcReader():

    def __init__(self, o2m=None):
        print("NFCReader initializing...")
        print("Insert or remove a smartcard in the system.")
        print("")

        self.o2m = o2m

        self.cardmonitor = CardMonitor()
        self.cardobserver = PrintObserver()
        self.cardmonitor.addObserver(self.cardobserver)
        self.cardobserver.events.on_change += self.update_change
        
    def update_change(self, addedCards, removedCards, activeCards):
        # print('update change ! Added cards : {}, Removed cards : {}'.format(addedCards, removedCards))
        self.o2m.get_new_cards(addedCards, removedCards, activeCards)

    def loop(self):
        try:
            while True:
                sleep(10)
        except KeyboardInterrupt:
            print('interrupted!')
            self.close()

    def close(self):
        # don't forget to remove observer, or the
        # monitor will poll forever...
        self.cardmonitor.deleteObserver(self.cardobserver)
        print('Observer removed!')

if __name__ == '__main__':
    nfc = NfcReader()
    nfc.loop()
    