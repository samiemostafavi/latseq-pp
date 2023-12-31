import sys
import re
import queue
import json
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

from collections import deque

class RingBuffer:
    def __init__(self, size):
        self.size = size
        self.buffer = deque(maxlen=size)

    def append(self, item):
        self.buffer.append(item)

    def get_items(self):
        return list(self.buffer)
    
    def reverse_items(self):
        return list(reversed(self.buffer))

# Check if the command-line argument for the file is provided
if len(sys.argv) != 2:
    logger.error("Usage: python postprocess.py <filename>")
    sys.exit(1)

# Get the filename from the command-line argument
filename = sys.argv[1]

# Try to open the file
try:
    file = open(filename, 'r')
except FileNotFoundError:
    print(f"File not found: {filename}")
except Exception as e:
    print(f"An error occurred: {str(e)}")


KW_R = 'ip.in'    # first, find the lines including this, then read 'PbufXXXXXX'.

# go back a few lines, find the first line that includes
KW_PDCPC = 'pdcp.cipher'
# and the same 'PbufXXXXXX'.

# go back more lines, find the first line that includes
KW_PDCP = 'pdcp.pdu'
# and 'snXX'. In this line, check lenYY

# go back more lines, find all lines that include
KW_RLC = 'rlc.queue'
# and 'snXX'. Read their 'lenZZ' and sum them up. Stop looking for more lines until the sum equals lenYY.

KW_RLC_TX = 'rlc.txpdu'

KW_MAC_1 = 'mac.sdu'
KW_MAC_2 = 'mac.harq'


# maximum number of lines to check
MAX_DEPTH = 500


# example retx:
'''
'''

# example:
'''
1699374983.040260 U mac.sdu--mac.harq len116::hqpid8.fm397.sl18.Mbuf67198768.Hbuf4101576416
1699374983.040257 U rlc.pdu--mac.sdu len38::tbs116.lcid4.fm397.sl18.Mbuf67198771
1699374983.040257 U rlc.queue--rlc.txpdu len38::tbs111.sn1966.pdulen38.R2buf3019904544.Mbuf67198771
1699374983.035740 U mac.sdu--mac.harq len116::hqpid13.fm397.sl9.Mbuf67198768.Hbuf4104164256
1699374983.035738 U rlc.pdu--mac.sdu len105::tbs116.lcid4.fm397.sl9.Mbuf67198777
1699374983.035738 U rlc.queue--rlc.txpdu len105::tbs105.sn1966.pdulen138.R2buf3019904544.Mbuf67198777
1699374983.035736 U rlc.pdu--mac.sdu len3::tbs116.lcid4.fm397.sl9.Mbuf67198771
1699374983.034837 U mac.sdu--mac.harq len24::hqpid15.fm397.sl7.M2buf25235248.Hbuf4105199392
1699374983.034836 U rlc.pdu--mac.sdu len21::tbs24.lcid4.fm397.sl7.M1buf25235251.M2buf25235248
1699374983.034835 U rlc.queue--rlc.txpdu len21::tbs21.sn1966.pdulen154.R2buf3019904544.M1buf25235251
1699374983.031532 U pdcp.pdu--rlc.queue len151::sduid0.queue151.R1buf2483032760.R2buf3019904544
1699374983.031523 U pdcp.cipher--pdcp.pdu len151::rb1.sduid0.PCbuf4268728416.R1buf2483032760
1699374983.031521 U pdcp.sdu--pdcp.cipher len151::rb1.sduid0.Pbuf4268738656.PCbuf4268728416
1699374983.031521 U ip.in--pdcp.sdu len148::rb1.sduid0.Pbuf4268738656
'''


ip_packets_counter = 0
previous_lines = RingBuffer(MAX_DEPTH)
print("[")
for line_number, line in enumerate(file, start=1):
    previous_lines.append(line)

    if KW_R in line:
        line = line.replace('\n', '')
        
        # Use regular expressions to extract the numbers
        timestamp_match = re.search(r'^(\d+\.\d+)', line)
        len_match = re.search(r'len(\d+)', line)
        pbuf_match = re.search(r'Pbuf(\d+)', line)

        if len_match and pbuf_match and timestamp_match:

            timestamp = float(timestamp_match.group(1))
            len_value = int(len_match.group(1))
            pbuf_value = int(pbuf_match.group(1))

            logger.debug(f"Found '{KW_R}' in line {line_number}, len:{len_value}, PBuf: {pbuf_value}, ts: {timestamp}")

            journey = {
                KW_R : {
                    'timestamp' : timestamp,
                    'length' : len_value,
                    'PBuf' : pbuf_value
                }
            }
            pbufp = f"Pbuf{pbuf_value}"

            # lets go back in lines
            prev_lines = previous_lines.reverse_items()

            # check for KW_PDCPC
            found_KW_PDCPC = False
            for id,prev_line in enumerate(prev_lines):
                if ("--"+KW_PDCPC in prev_line) and (pbufp in prev_line):
                    timestamp_match = re.search(r'^(\d+\.\d+)', prev_line)
                    len_match = re.search(r'len(\d+)', prev_line)
                    pcbuf_match = re.search(r'PCbuf(\d+)', prev_line)
                    if len_match and pcbuf_match and timestamp_match:
                        timestamp = float(timestamp_match.group(1))
                        len_value = int(len_match.group(1))
                        pcbuf_value = int(pcbuf_match.group(1))
                    else:
                        logger.warning(f"For {KW_PDCPC}, could not found timestamp or length in line {line_number-id-1}. Skipping this '{KW_R}' journey")
                        break

                    logger.debug(f"Found '{KW_PDCPC}' and '{pbufp}' in line {line_number-id-1}, len:{len_value}, timestamp: {timestamp}, PCbuf: {pcbuf_value}")
                    journey[KW_PDCPC] = {
                        'timestamp' : timestamp,
                        'length' : len_value,
                        'PCBuf' : pcbuf_value
                    }
                    pcbufp = f"PCbuf{pcbuf_value}"
                    found_KW_PDCPC = True
                    break

            if not found_KW_PDCPC:
                logger.warning(f"Could not find '{KW_PDCPC}' and '{pbufp}' in {len(prev_lines)} lines before {line_number}. Skipping this '{KW_R}' journey")
                exit(0)
                continue

            # check for KW_PDCP
            found_KW_PDCP = False
            for id,prev_line in enumerate(prev_lines):
                if ("--"+KW_PDCP in prev_line) and (pcbufp in prev_line):
                    timestamp_match = re.search(r'^(\d+\.\d+)', prev_line)
                    len_match = re.search(r'len(\d+)', prev_line)
                    r1buf_match = re.search(r'R1buf(\d+)', prev_line)
                    if len_match and timestamp_match and r1buf_match:
                        timestamp = float(timestamp_match.group(1))
                        len_value = int(len_match.group(1))
                        r1buf_value = int(r1buf_match.group(1))
                    else:
                        logger.warning(f"For {KW_PDCP}, could not found timestamp or length in in line {line_number-id-1}. Skipping this '{KW_R}' journey")
                        break

                    logger.debug(f"Found '{KW_PDCP}' and '{pcbufp}' in line {line_number-id-1}, len:{len_value}, timestamp: {timestamp}")
                    journey[KW_PDCP] = {
                        'timestamp' : timestamp,
                        'length' : len_value,
                        'R1buf' : r1buf_value
                    }
                    r1bufp = f"R1buf{r1buf_value}"
                    found_KW_PDCP = True
                    break
            
            if not found_KW_PDCP:
                logger.warning(f"Could not find '{KW_PDCP}' and '{pcbufp}' in {len(prev_lines)} lines before {line_number}. Skipping this '{KW_R}' journey")
                continue


            # check for KW_RLC
            found_KW_RLC = False
            for id,prev_line in enumerate(prev_lines):
                if ("--"+KW_RLC in prev_line) and (r1bufp in prev_line):
                    timestamp_match = re.search(r'^(\d+\.\d+)', prev_line)
                    len_match = re.search(r'len(\d+)', prev_line)
                    r2buf_match = re.search(r'R2buf(\d+)', prev_line)
                    q_match = re.search(r'queue(\d+)', prev_line)
                    if len_match and timestamp_match and r2buf_match and q_match:
                        timestamp = float(timestamp_match.group(1))
                        len_value = int(len_match.group(1))
                        r2buf_value = int(r2buf_match.group(1))
                        queue_value = int(q_match.group(1))
                    else:
                        logger.warning(f"For {KW_RLC}, could not found timestamp or length in in line {line_number-id-1}. Skipping this '{KW_R}' journey")
                        break

                    logger.debug(f"Found '{KW_RLC}' and '{r1bufp}' in line {line_number-id-1}, len:{len_value}, timestamp: {timestamp}")
                    journey[KW_RLC] = {
                        'timestamp' : timestamp,
                        'length' : len_value,
                        'R2buf' : r2buf_value,
                        'queue' : queue_value,
                        'segments' : {},
                    }
                    r2bufp = f"R2buf{r2buf_value}"
                    found_KW_RLC = True
                    break
            
            if not found_KW_RLC:
                logger.warning(f"Could not find '{KW_RLC}' and '{r1bufp}' in {len(prev_lines)} lines before {line_number}. Skipping this '{KW_R}' journey")
                continue

            
            # check for KW_RLC_TX
            RLC_ARR = []
            lengths = []
            for id,prev_line in enumerate(prev_lines):
                if ("--"+KW_RLC_TX in prev_line) and (r2bufp in prev_line):
                    timestamp_match = re.search(r'^(\d+\.\d+)', prev_line)
                    len_match = re.search(r'len(\d+)', prev_line)
                    leno_match = re.search(r'leno(\d+)', prev_line)
                    tbs_match = re.search(r'tbs(\d+)\.', prev_line)
                    sn_match = re.search(r'sn(\d+)\.', prev_line)
                    m1buf_match = re.search(r'M1buf(\d+)', prev_line)
                    if len_match and timestamp_match and tbs_match and sn_match and m1buf_match:
                        timestamp = float(timestamp_match.group(1))
                        len_value = int(len_match.group(1))
                        leno_value = int(leno_match.group(1))
                        tbs_value = int(tbs_match.group(1))
                        sn_value = int(sn_match.group(1))
                        m1buf_value = int(m1buf_match.group(1))
                    else:
                        logger.warning(f"For {KW_RLC_TX}, could not found timestamp, length, or M1buf in in line {line_number-id-1}. Skipping this '{KW_R}' journey")
                        break

                    logger.debug(f"Found '{KW_RLC_TX}' and '{r2bufp}' in line {line_number-id-1}, len:{len_value}, timestamp: {timestamp}, Mbuf:{m1buf_value}, sn: {sn_value}, tbs: {tbs_value}")
                    lengths.append(len_value)
                    rlc_tx_reass_dict = {
                        'M1buf' : m1buf_value,
                        'sn' : sn_value,
                        'tbs' : tbs_value,
                        'timestamp' : timestamp,
                        'length' : len_value,
                        'leno' : leno_value,
                    }
                    m1bufp = f"M1buf{m1buf_value}"

                    # Check RLC_decoded for each RLC_reassembeled
                    found_MAC_1 = False
                    for jd,prev_ljne in enumerate(prev_lines):
                        if ("--"+KW_MAC_1 in prev_ljne) and (m1bufp in prev_ljne):
                            timestamp_match = re.search(r'^(\d+\.\d+)', prev_ljne)
                            len_match = re.search(r'len(\d+)', prev_ljne)
                            fm_match = re.search(r'fm(\d+)', prev_ljne)
                            sl_match = re.search(r'sl(\d+)', prev_ljne)
                            lcid_match = re.search(r'lcid(\d+)', prev_ljne)
                            tbs_match = re.search(r'tbs(\d+)', prev_ljne)
                            m2buf_match = re.search(r'M2buf(\d+)', prev_ljne)
                            if len_match and timestamp_match and fm_match and sl_match and lcid_match and tbs_match and m2buf_match:
                                timestamp = float(timestamp_match.group(1))
                                len_value = int(len_match.group(1))
                                fm_value = int(fm_match.group(1))
                                sl_value = int(sl_match.group(1))
                                lcid_value = int(lcid_match.group(1))
                                tbs_value = int(tbs_match.group(1))
                                m2buf_value = int(m2buf_match.group(1))
                            else:
                                logger.warning(f"For {KW_MAC_1}, could not find properties in line {line_number-jd-1}. Skipping this '{KW_R}' journey")
                                break

                            logger.debug(f"Found '{KW_MAC_1}' and '{m1bufp}' in line {line_number-jd-1}, len:{len_value}, timestamp: {timestamp}, frame: {fm_value}, slot: {sl_value}")

                            mac_1_dict = {
                                'lcid': lcid_value,
                                'tbs': tbs_value,
                                'frame': fm_value,
                                'slot': sl_value,
                                'timestamp' : timestamp,
                                'length' : len_value,
                                'M2buf' : m2buf_value,
                            }
                            m2bufp = f"M2buf{m2buf_value}"
                            found_MAC_1 = True
                            break

                    if not found_MAC_1:
                        logger.warning(f"Could not find '{KW_MAC_1}' and '{m1bufp}' in {len(prev_lines)} lines before {line_number}. Skipping this '{KW_R}' journey")
                        continue

                    # Check RLC_decoded for each RLC_reassembeled
                    found_MAC_2 = False
                    for jd,prev_ljne in enumerate(prev_lines):
                        if ("--"+KW_MAC_2 in prev_ljne) and (m2bufp in prev_ljne):
                            timestamp_match = re.search(r'^(\d+\.\d+)', prev_ljne)
                            len_match = re.search(r'len(\d+)', prev_ljne)
                            fm_match = re.search(r'fm(\d+)', prev_ljne)
                            sl_match = re.search(r'sl(\d+)', prev_ljne)
                            hqpid_match = re.search(r'hqpid(\d+)', prev_ljne)
                            if len_match and timestamp_match and fm_match and sl_match and hqpid_match:
                                timestamp = float(timestamp_match.group(1))
                                len_value = int(len_match.group(1))
                                fm_value = int(fm_match.group(1))
                                sl_value = int(sl_match.group(1))
                                hqpid_value = int(hqpid_match.group(1))
                            else:
                                logger.warning(f"For {KW_MAC_2}, could not find properties in line {line_number-jd-1}. Skipping this '{KW_R}' journey")
                                break

                            logger.debug(f"Found '{KW_MAC_2}' and '{m2bufp}' in line {line_number-jd-1}, len:{len_value}, timestamp: {timestamp}, frame: {fm_value}, slot: {sl_value}")

                            mac_2_dict = {
                                'hqpid': hqpid_value,
                                'frame': fm_value,
                                'slot': sl_value,
                                'timestamp' : timestamp,
                                'length' : len_value,
                            }
                            found_MAC_2 = True
                            break

                    if not found_MAC_2:
                        logger.warning(f"Could not find '{KW_MAC_2}' and '{m2bufp}' in {len(prev_lines)} lines before {line_number}. Skipping this '{KW_R}' journey")
                        mac_2_dict = {}

                    RLC_ARR.append(
                        {
                            KW_RLC_TX : rlc_tx_reass_dict,
                            KW_MAC_1 : mac_1_dict,
                            KW_MAC_2 : mac_2_dict
                        }
                    )
                    if sum(lengths) >= journey[KW_RLC]['length']:
                        break
            
            journey[KW_RLC]['segments'] = RLC_ARR

            if ip_packets_counter > 0:
                print(",", end="")

            print(json.dumps(journey))

            ip_packets_counter = ip_packets_counter+1

        else:
            logger.error(f"Couldn't extract values from the line {line_number}")
            break
else:
    logger.debug(f"'{KW_R}' no more in the file.")

logger.info(f"Found {ip_packets_counter} ip packets.")

print("]")