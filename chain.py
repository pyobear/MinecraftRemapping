#!/usr/bin/python

# Given obf<->MCP and obf<->CB mappings, generate MCP<->CB mappings

import sys, os
import srglib

global verbose

# Load a srg
# TODO: refactor into srglib.py!
def process(filename):
    reverse = False
    if filename.startswith("^"):
        filename = filename[1:]
        reverse = True
    f = file(filename)
    classes_o2d = {}; classes_d2o = {}
    fields_o2d = {}; fields_d2o = {}
    methods_o2d = {}; methods_d2o = {}
    csrg_lines = []
    for line in f.readlines():
        line = line.strip()
        if len(line) == 0: continue
        if ": " in line:
            # standard srg
            kind, argsString = line.split(": ")
            args = argsString.split(" ")
            if kind == "PK":  # package
                continue 
            elif kind == "CL": # class
                obfName, deobName = args
                classes_o2d[obfName] = deobName
                classes_d2o[deobName] = obfName
            elif kind == "FD": # field
                obfName, deobName = args
                fields_o2d[obfName] = deobName
                fields_d2o[deobName] = obfName
            elif kind == "MD": # method
                obfName, obfSig, deobName, deobSig = args

                obfKey = obfName + " " + obfSig
                deobKey = deobName + " " + deobSig
                methods_o2d[obfKey] = deobKey
                methods_d2o[deobKey] = obfKey
            else:
                assert "Unknown type " + kind
        else:
            # compact srg
            args = line.split(" ")
            if len(args) == 2: # class
                obfName, deobName = args
                if obfName.endswith("/"): continue # package
                classes_o2d[obfName] = deobName
                classes_d2o[deobName] = obfName
            # defer field/method mapping until read complete class map (TODO: refactor)
            elif len(args) == 3: # field
                csrg_lines.append(args)
            elif len(args) == 4: # method
                csrg_lines.append(args)
            else:
                assert "Unknown mapping file format "+line

    if len(csrg_lines) > 0:
        for args in csrg_lines:
            if len(args) == 3: # field
                obfClassName, obfFieldName, deobFieldName = args
                obfName = obfClassName + "/" + obfFieldName
                deobName = classes_o2d[obfClassName] + "/" + deobFieldName

                fields_o2d[obfName] = deobName
                fields_d2o[deobName] = obfName
            elif len(args) == 4: # method
                obfClassName, obfMethodName, obfSig, deobMethodName = args
                obfName = obfClassName + "/" + obfMethodName
                deobName = classes_o2d[obfClassName] + "/" + deobMethodName

                obfKey = obfName + " " + obfSig
                deobKey = deobName + " " + srglib.remapSig(obfSig, classes_o2d)

                methods_o2d[obfKey] = deobKey
                methods_d2o[deobKey] = obfKey
            else:
                assert "Unknown mapping file format "+line


    if not reverse:
        return {"CL": classes_o2d, "FD": fields_o2d, "MD": methods_o2d}
    else:
        return {"CL": classes_d2o, "FD": fields_d2o, "MD": methods_d2o}

# Load fields/methods.csv mapping "searge" name (func_XXX/field_XXX) to descriptive MCP name
def loadDescriptiveNamesCSV(fn):
    f = file(fn)
    d = {}
    for line in f.readlines():
        tokens = line.split(",",3)
        if tokens[0] == "searge": continue
        searge,name,side,desc = tokens
        if side == "0": continue # 2=joined, 1=server-side, 0=client-side. Skip client, include server and joined
        d[searge] = name
    return d

def chain(mcpdir, cbsrg):
    if mcpdir.endswith("srg"):
        # only chain srgs
        mcpsrg = mcpdir
        fields_fn = methods_fn = None
    elif mcpdir.endswith("/"):
        # also translate descriptive names through MCP's fields/methods.csv
        mcpsrg = mcpdir + "packaged.srg"    # FML uses multi-level packages (not joined.srg)
        #mcpsrg = mcpdir + "joined.srg"    # flat namespace
        if not os.path.exists(mcpsrg):
            mcpsrg = mcpdir + "server.srg"  # old MCP with flat namespace
        if not os.path.exists(mcpsrg):
            print "no .srg found in %s" % (mcpdir,)
            raise SystemExit

        fields_fn = mcpdir + "fields.csv"
        methods_fn = mcpdir + "methods.csv"
    else:
        assert False, "argument must be srg or mcp dir with .srg, fields.csv, and methods.csv"

    mcp = process(mcpsrg)
    if not cbsrg == "-":
        cb = process(cbsrg)
    else:
        cb = None  # special case - no chaining, used for extracting MCP descriptions

    # Map MCP indexed names to descriptive names
    if fields_fn and methods_fn:
        descriptiveFieldNames = loadDescriptiveNamesCSV(fields_fn)
        descriptiveMethodNames = loadDescriptiveNamesCSV(methods_fn)
    else:
        descriptiveFieldNames = descriptiveMethodNames = {}

    def descriptiveName(mcpIndexedNameSig):
        # methods are name, space, signature
        if " " in mcpIndexedNameSig:
            mcpIndexedName, sig = mcpIndexedNameSig.split(" ")
            sig = " " + sig
        else:
            mcpIndexedName = mcpIndexedNameSig
            sig = ""

        # translate name, preserving package
        tokens = mcpIndexedName.split("/")
        firstName = tokens[:-1]
        lastName = tokens[-1]
        if lastName.startswith("field_"):
            newName = descriptiveFieldNames.get(lastName, lastName)
        elif lastName.startswith("func_"):
            newName = descriptiveMethodNames.get(lastName, lastName)
        else:
            newName = lastName

        return "/".join(firstName + [newName]) + sig

    for kind in ("CL", "FD", "MD"):
        mapMCP = mcp[kind]
        if cb is not None:
            mapCB = cb[kind]

            missing = set(mapMCP.keys()) - set(mapCB.keys())
            if len(missing) != 0 and verbose:
                print "CB mappings missing from MCP mappings: %s" % (missing,)
                import pprint
                print "=== mapMCP ==="
                pprint.pprint(mapMCP)
                print "=== mapCB ==="
                pprint.pprint(mapCB)
                print "== missing ==="
                pprint.pprint(missing)

            surplus = set(mapCB.keys()) - set(mapMCP.keys())
            if len(surplus) != 0:
               #print "CB mappings has extra mappings not in MCP: %s" % (surplus,) # no problem, probably just constructors (no rename)
               pass

        for obf in sorted(mapMCP.keys()):
            if cb is not None:
                if not mapCB.has_key(obf) or not mapMCP.has_key(obf): continue

                print "%s: %s %s" % (kind, mapCB[obf], descriptiveName(mapMCP[obf]))
            else:
                print "%s: %s %s" % (kind, obf, descriptiveName(mapMCP[obf]))

def main():
    global verbose

    verbose = False

    if len(sys.argv) < 3:
        print "chain srg given obf<->MCP and obf<->CB to CB<->MCP"
        print "Usage: %s clean-mcpdir/conf cb-server.srg [-v]" % (sys.argv[0],)
        print "Examples:"
        print "Translate through .srg and descriptive fields.csv/methods.csv:"
        print "\t%s ../mcpXXX-clean/conf/ obf2cb.srg > cb2mcp.srg" % (sys.argv[0],)
        print "\t%s ../mcpXXX-pkgd/conf/ obf2cb.srg > cb2pkgmcp.srg" % (sys.argv[0],)
        print "Translate only through .srg, leaving indexed func_XXX/field_XXX names:"
        print "\t%s ../mcpXXX-clean/conf/server.srg obf2cb.srg" % (sys.argv[0],)
        print "Only extract descriptions (no chaining):"
        print "\t%s ../mcpXXX-clean/conf/ -" % (sys.argv[0],)
        raise SystemExit

    mcpdir = sys.argv[1]
    cbsrg = sys.argv[2]

    verbose = "-v" in sys.argv

    chain(mcpdir, cbsrg)

if __name__ == "__main__":
    main()
