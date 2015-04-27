# -*- coding: utf-8 -*-

#   Copyright (c) 2010-2014, MIT Probabilistic Computing Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import contextlib
import os
import pexpect
import pytest
import tempfile


TIMEOUT = 2
ROOT = os.path.dirname(os.path.abspath(__file__))
DHA_CSV = os.path.join(ROOT, '..', '..', 'tests', 'dha.csv')
THOOKS_PY = os.path.join(ROOT, 'thooks.py')

READ_DATA = '''
-- do something that fails (should not kick us out)
.csv dha

-- create a table properly
.csv dha {0}

-- single line BQL
SELECT name FROM dha LIMIT 2;

-- mulitline BQL. 2nd line is space indented; 3rd line is tabbed.
SELECT name FROM dha
    ORDER BY name ASC
    LIMIT 5;
'''.format(DHA_CSV)


class spawnjr(pexpect.spawn):
    def __init__(self, *args, **kwargs):
        if 'timeout' not in kwargs:
            kwargs['timeout'] = TIMEOUT
        super(spawnjr, self).__init__(*args, **kwargs)
    def expectprompt(self, output, tweak=None):
        x = self.expect('bayeslite> ')
        before = self.before
        if tweak is not None:
            before = tweak(before)
        assert before == '\r\n'.join(output + [''])
        return x


@contextlib.contextmanager
def read_data():
    with tempfile.NamedTemporaryFile(prefix='bayeslite-shell') as temp:
        with open(temp.name, 'w') as f:
            f.write(READ_DATA)
        yield temp.name


@pytest.fixture
def spawnbdb():
    c = spawnjr('bayeslite --no-init-file --debug')
    c.delaybeforesend = 0
    c.expectprompt([
        "Welcome to the Bayeslite shell.",
        "Type `.help' for help.",
    ])
    return c


@pytest.fixture
def spawntable():
    c = spawnbdb()
    cmd = '.csv dha %s' % (DHA_CSV,)
    c.sendline(cmd)
    # XXX Kludge to strip control characters introduced by the pty
    # when the line wraps, which vary from system to system (some use
    # backspace; some use carriage return; some insert spaces).
    def remove_control(s):
        return s.translate(None, ''.join(map(chr, range(32 + 1) + [127])))
    c.expectprompt([remove_control(cmd)],
        tweak=lambda s: remove_control(s) + '\r\n')
    return 'dha', c


@pytest.fixture
def spawngen(spawntable):
    table, c = spawntable
    c.sendline('.guess dha_cc %s' % (table,))
    c.expectprompt(['.guess dha_cc %s' % (table,)])
    return 'dha_cc', c


def an_error_probably_happened(string):
    error_clues = ['error', 'traceback', 'exception']
    stringlower = string.lower()
    return any(x in stringlower for x in error_clues)


# Tests begin
# ````````````````````````````````````````````````````````````````````````````
def test_shell_loads(spawnbdb):
    c = spawnbdb


def test_python_expression(spawnbdb):
    c = spawnbdb
    c.sendline('.python 2 * 3')
    c.expectprompt(['.python 2 * 3', '6'])


def test_help_returns_list_of_commands(spawnbdb):
    c = spawnbdb
    c.sendline('.help')
    c.expectprompt([
        '.help',
        '     .codebook    load codebook for table',
        '          .csv    create table from CSV file',
        '     .describe    describe BayesDB entities',
        '        .guess    guess data generator',
        '         .help    show help for commands',
        '         .hook    add custom commands from a python source file',
        ' .legacymodels    load legacy models',
        '       .python    evaluate a Python expression',
        '         .read    read a file of shell commands',
        '          .sql    execute a SQL query',
        '        .trace    trace queries',
        '      .untrace    untrace queries',
        "Type `.help <cmd>' for help on the command <cmd>.",
    ])


def test_dot_csv(spawnbdb):
    c = spawnbdb
    cmd = '.csv dha %s' % (DHA_CSV,)
    c.sendline(cmd)
    def remove_control(s):
        return s.translate(None, ''.join(map(chr, range(32 + 1) + [127])))
    c.expectprompt([remove_control(cmd)],
        tweak=lambda s: remove_control(s) + '\r\n')


def test_describe_columns_without_generator(spawntable):
    table, c = spawntable
    c.sendline('.describe columns %s' % (table,))
    c.expect('No such generator: %s' % (table,))


def test_bql_select(spawntable):
    table, c = spawntable
    query = 'SELECT name FROM %s ORDER BY name ASC LIMIT 5;' % (table,)
    c.sendline(query)
    c.expectprompt([
        query,
        '             NAME',
        '-----------------',
        '       Abilene TX',
        '         Akron OH',
        'Alameda County CA',
        '        Albany GA',
        '        Albany NY',
    ])


def test_guess(spawntable):
    table, c = spawntable
    cmd = '.guess dha_cc dha'
    c.sendline(cmd)
    c.expectprompt([cmd])


def test_sql(spawntable):
    table, c = spawntable
    cmd = '.sql pragma table_info(bayesdb_column)'
    c.sendline(cmd)
    c.expectprompt([
        cmd,
        'cid |        name |    type | notnull | dflt_value | pk',
        '----+-------------+---------+---------+------------+---',
        '  0 |     tabname |    TEXT |       1 |       None |  1',
        '  1 |       colno | INTEGER |       1 |       None |  2',
        '  2 |        name |    TEXT |       1 |       None |  0',
        '  3 |   shortname |    TEXT |       0 |       None |  0',
        '  4 | description |    TEXT |       0 |       None |  0',
    ])


def test_describe_column_with_generator(spawngen):
    gen, c = spawngen
    c.sendline('.describe models %s' % (gen,))
    c.expectprompt([
        '.describe models %s' % (gen,),
        'modelno | iterations',
        '--------+-----------',
    ])
    c.sendline('.describe columns %s' % (gen,))
    c.expectprompt([
        '.describe columns %s' % (gen,),
        'colno |                name |  stattype | shortname',
        '------+---------------------+-----------+----------',
        '    1 |         N_DEATH_ILL | numerical |      None',
        '    2 |       TTL_MDCR_SPND | numerical |      None',
        '    3 |       MDCR_SPND_INP | numerical |      None',
        '    4 |      MDCR_SPND_OUTP | numerical |      None',
        '    5 |       MDCR_SPND_LTC | numerical |      None',
        '    6 |      MDCR_SPND_HOME | numerical |      None',
        '    7 |      MDCR_SPND_HSPC | numerical |      None',
        '    8 |    MDCR_SPND_AMBLNC | numerical |      None',
        '    9 |       MDCR_SPND_EQP | numerical |      None',
        '   10 |     MDCR_SPND_OTHER | numerical |      None',
        '   11 |           TTL_PARTB | numerical |      None',
        '   12 |     PARTB_EVAL_MGMT | numerical |      None',
        '   13 |         PARTB_PROCS | numerical |      None',
        '   14 |          PARTB_IMAG | numerical |      None',
        '   15 |         PARTB_TESTS | numerical |      None',
        '   16 |         PARTB_OTHER | numerical |      None',
        '   17 |    HOSP_REIMB_P_DCD | numerical |      None',
        '   18 |     HOSP_DAYS_P_DCD | numerical |      None',
        '   19 |    REIMB_P_PTNT_DAY | numerical |      None',
        '   20 |    HOSP_REIMB_RATIO | numerical |      None',
        '   21 |      HOSP_DAY_RATIO | numerical |      None',
        '   22 |   REIMB_P_DAY_RATIO | numerical |      None',
        '   23 |       MD_PYMT_P_DCD | numerical |      None',
        '   24 |      MD_VISIT_P_DCD | numerical |      None',
        '   25 |     PYMT_P_MD_VISIT | numerical |      None',
        '   26 | MD_VISIT_PYMT_RATIO | numerical |      None',
        '   27 |      MD_VISIT_RATIO | numerical |      None',
        '   28 |  PYMT_P_VISIT_RATIO | numerical |      None',
        '   29 |           HOSP_BEDS | numerical |      None',
        '   30 |         TTL_IC_BEDS | numerical |      None',
        '   31 |          HI_IC_BEDS | numerical |      None',
        '   32 |         INT_IC_BEDS | numerical |      None',
        '   33 |       MED_SURG_BEDS | numerical |      None',
        '   34 |            SNF_BEDS | numerical |      None',
        '   35 |           TOTAL_FTE | numerical |      None',
        '   36 |              MS_FTE | numerical |      None',
        '   37 |              PC_FTE | numerical |      None',
        '   38 |         MS_PC_RATIO | numerical |      None',
        '   39 |             RNS_REQ | numerical |      None',
        '   40 |    HOSP_DAYS_P_DCD2 | numerical |      None',
        '   41 |   TTL_IC_DAYS_P_DCD | numerical |      None',
        '   42 |    HI_IC_DAYS_P_DCD | numerical |      None',
        '   43 |   INT_IC_DAYS_P_DCD | numerical |      None',
        '   44 | MED_SURG_DAYS_P_DCD | numerical |      None',
        '   45 |      SNF_DAYS_P_DCD | numerical |      None',
        '   46 |  TTL_MD_VISIT_P_DCD | numerical |      None',
        '   47 |      MS_VISIT_P_DCD | numerical |      None',
        '   48 |      PC_VISIT_P_DCD | numerical |      None',
        '   49 |   MS_PC_RATIO_P_DCD | numerical |      None',
        '   50 |     HHA_VISIT_P_DCD | numerical |      None',
        '   51 |       PCT_DTHS_HOSP | numerical |      None',
        '   52 |      PCT_DTHS_W_ICU | numerical |      None',
        '   53 |       PCT_DTHS_HSPC | numerical |      None',
        '   54 |     HSPC_DAYS_P_DCD | numerical |      None',
        '   55 |      PCT_PTNT_10_MD | numerical |      None',
        '   56 |          N_MD_P_DCD | numerical |      None',
        '   57 |     TTL_COPAY_P_DCD | numerical |      None',
        '   58 |      MD_COPAY_P_DCD | numerical |      None',
        '   59 |     EQP_COPAY_P_DCD | numerical |      None',
        '   60 |          QUAL_SCORE | numerical |      None',
        '   61 |           AMI_SCORE | numerical |      None',
        '   62 |           CHF_SCORE | numerical |      None',
        '   63 |         PNEUM_SCORE | numerical |      None',
    ])


def test_hook(spawnbdb):
    c = spawnbdb
    c.sendline('.hook %s' % (THOOKS_PY,))
    c.expectprompt([
        '.hook %s' % (THOOKS_PY,),
        'added command ".myhook"',
    ])
    c.sendline('.help')
    c.expectprompt([
        '.help',
        '     .codebook    load codebook for table',
        '          .csv    create table from CSV file',
        '     .describe    describe BayesDB entities',
        '        .guess    guess data generator',
        '         .help    show help for commands',
        '         .hook    add custom commands from a python source file',
        ' .legacymodels    load legacy models',
        '       .myhook    myhook help string',
        '       .python    evaluate a Python expression',
        '         .read    read a file of shell commands',
        '          .sql    execute a SQL query',
        '        .trace    trace queries',
        '      .untrace    untrace queries',
        "Type `.help <cmd>' for help on the command <cmd>.",
    ])
    c.sendline('.help myhook')
    c.expectprompt([
        '.help myhook',
        '.myhook <string>',
    ])
    c.sendline('.myhook zoidberg')
    c.expectprompt([
        '.myhook zoidberg',
        'john zoidberg',
    ])


def test_read_nonsequential(spawnbdb):
    c = spawnbdb
    with read_data() as fname:
        c.sendline('.read %s' % (fname,))
        c.expectprompt([
            '.read %s' % (fname,),
            'Usage: .csv <table> </path/to/data.csv>',
            '      NAME',
            '----------',
            'Abilene TX',
            '  Akron OH',
            '             NAME',
            '-----------------',
            '       Abilene TX',
            '         Akron OH',
            'Alameda County CA',
            '        Albany GA',
            '        Albany NY',
            '--DEBUG: .read complete',
        ])


def test_read_nonsequential_verbose(spawnbdb):
    c = spawnbdb
    with read_data() as fname:
        c.sendline('.read %s' % (fname,))
        c.expectprompt([
            '.read %s' % (fname,),
            'Usage: .csv <table> </path/to/data.csv>',
            '      NAME',
            '----------',
            'Abilene TX',
            '  Akron OH',
            '             NAME',
            '-----------------',
            '       Abilene TX',
            '         Akron OH',
            'Alameda County CA',
            '        Albany GA',
            '        Albany NY',
            '--DEBUG: .read complete',
        ])
